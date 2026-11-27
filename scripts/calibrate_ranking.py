"""对国内搜索和博主的整批候选做离线留出评估。每行输入一条 JSON。

batch 标明同一次搜索，split_group 可按账号、词组或日期隔离。label (0/1) 标记
相对表现异常，borrow (0/1/2) 标记项目可借用程度。按来源顺序记录原始 response，
提供 platform 和 url。可填 observed_at 或当时的 age_days。兼容旧 group 分组。
使用示例及各指标口径见 docs/参考选片评审.md。
"""

import argparse, hashlib, itertools, json, math, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.adapters import normalize
from server import discovery, ranking

KEYS = [
    "engagement",
    "efficiency",
    "account_lift",
    "category_lift",
    "freshness",
    "reusability",
]
DEFAULT = {
    "engagement": 0.3,
    "efficiency": 0.25,
    "account_lift": 0.2,
    "category_lift": 0.15,
    "freshness": 0.05,
    "reusability": 0.05,
}


def auc(scores, labels):
    """Mann–Whitney AUC；缺失分数的样本不参与。"""
    pairs = [(s, l) for s, l in zip(scores, labels) if s is not None]
    pos = [s for s, l in pairs if l]
    neg = [s for s, l in pairs if not l]
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return round(wins / (len(pos) * len(neg)), 4)


def load(path, split_key="split_group"):
    rows, errors = [], []
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            sample = json.loads(line)
            content = normalize(sample["response"], sample["platform"], sample.get("url", ""))
            # Never age an evaluation sample relative to the day the evaluator reruns.
            observed = sample.get("observed_at")
            if observed is not None:
                observed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
                if not observed.tzinfo:
                    raise ValueError("observed_at 需要包含时区")
            content["age_days"] = discovery.parse_age_days(content["evidence"], observed.timestamp()) if observed else None
            ident = content["evidence"].get("note_id") or content["evidence"].get("aweme_id") or content["evidence"].get("id")
            entry = sample.get("entry", "keyword")
            if entry not in ("keyword", "creator"):
                raise ValueError("entry 应是 keyword 或 creator")
            label = sample["label"]
            borrow = sample.get("borrow")
            if type(label) is not int or label not in (0, 1):
                raise ValueError("label 应为 0 或 1")
            if borrow is not None and (type(borrow) is not int or borrow not in (0, 1, 2)):
                raise ValueError("borrow 应为 0、1 或 2")
            batch = sample.get("batch") or sample.get("group")
            split = sample.get(split_key, batch if split_key == "split_group" else None)
            if any(x is not None and (not isinstance(x, str) or not x.strip()) for x in (batch, split)):
                raise ValueError("批次与留出组须为非空文本")
            for key in ("age_days", "account_median", "category_median", "reusability"):
                if sample.get(key) is not None:
                    content[key] = sample[key]
            rows.append(
                {
                    "line": n, "entry":entry, "item_key": f"{sample['platform']}:{ident}" if ident else content["url"],
                    "label": label, "borrow": borrow, "batch": batch, "split": split,
                    "content": content,
                }
            )
        except Exception as e:
            errors.append({"line": n, "error": str(e)[:200]})
    return rows, errors


def add_baselines(rows):
    groups = {}
    for r in rows:
        if r["batch"]:
            groups.setdefault(r["batch"], []).append(ranking.engagement(r["content"]))
    for r in rows:
        field = "account_median" if r.get("entry") == "creator" else "category_median"
        if r["batch"] and r["content"].get(field) is None:
            r["content"][field] = ranking.median(groups[r["batch"]])


def compositions(total, parts):
    """把 total 份权重分给 parts 个维度的所有方式（每份 ≥ 0）。"""
    for bars in itertools.combinations(range(total + parts - 1), parts - 1):
        prev, out = -1, []
        for b in bars:
            out.append(b - prev - 1)
            prev = b
        out.append(total + parts - 2 - prev)
        yield out


def grid(rows, step):
    labels = [r["label"] for r in rows]
    comps = [ranking.score(r["content"], DEFAULT)["components"] for r in rows]
    units = int(round(1 / step))
    best = None
    for combo in compositions(units, len(KEYS)):
        weights = {k: round(c * step, 4) for k, c in zip(KEYS, combo)}
        scores = [ranking.weighted_score(c, weights) for c in comps]
        if any(score is None and "engagement" in components for score, components in zip(scores, comps)):
            continue
        value = auc(scores, labels)
        if value is not None and (best is None or value > best[0]):
            best = (value, weights)
    return best


def partition(rows, requested):
    groups = {r["split"] for r in rows}
    if requested:
        if not set(requested) <= groups:
            raise ValueError("指定的留出组不在样本中")
        hold = set(requested)
    elif len(groups) >= 2 and None not in groups:
        ordered = sorted(groups, key=lambda key: hashlib.sha256(key.encode()).digest())
        hold = set(ordered[:max(1, len(ordered) // 4)])
    else:
        return rows, []
    if None in groups or hold == groups or any(not r["batch"] for r in rows):
        raise ValueError("留出评估需要每行标注 batch 和分组，并至少保留一个训练组")
    train = [r for r in rows if r["split"] not in hold]
    test = [r for r in rows if r["split"] in hold]
    if {r["batch"] for r in train} & {r["batch"] for r in test}:
        raise ValueError("同一批候选不能横跨训练与留出组，请调整分组")
    def identities(row):
        url = row["content"].get("url") or ""
        keys = {url, row.get("item_key")} - {None, ""}
        parts = urlsplit(url)
        path = parts.path.strip("/").split("/")
        if parts.hostname in ("www.xiaohongshu.com", "www.douyin.com") and path[-1]:
            if path[:-1] in (["explore"], ["discovery", "item"]) and parts.hostname == "www.xiaohongshu.com":
                keys.add("xhs:" + path[-1])
            if path[:-1] == ["video"] and parts.hostname == "www.douyin.com":
                keys.add("douyin:" + path[-1])
        return keys
    if any(not identities(row) for row in rows):
        raise ValueError("留出评估需要每条样本提供原片 URL 或稳定的平台作品 ID")
    held_keys = set().union(*(identities(r) for r in test))
    train = [r for r in train if held_keys.isdisjoint(identities(r))]
    if not train:
        raise ValueError("去除与留出集重复的原片后缺少训练数据")
    return train, test


def top_three(rows, weights):
    batches = defaultdict(list)
    for row in rows:
        batches[row["batch"]].append(row)
    strategies = {"source_order":None, "likes":"likes", **weights}
    result = {}
    for name, method in strategies.items():
        useful, slots, returned, ndcg = 0, 0, 0, []
        for batch in batches.values():
            if any(r["borrow"] is None for r in batch):
                continue
            def key(row):
                content = row["content"]
                if method == "likes":
                    value = content.get("likes")
                    return value is None, -(value or 0)
                rank = ranking.score(content, method)
                return rank["evidence_status"] == "needs_metrics", rank["score"] is None, -(rank["score"] or 0)
            ordered = sorted(batch, key=key) if method else batch
            if isinstance(method, dict):
                ordered = [r for r in ordered if ranking.engagement(r["content"]) is not None]
            chosen = [r["borrow"] for r in ordered[:3]]
            ideal = sorted((r["borrow"] for r in batch), reverse=True)[:3]
            def dcg(grades):
                return sum((2 ** grade - 1) / math.log2(i + 2) for i, grade in enumerate(grades))
            useful += sum(g > 0 for g in chosen)
            returned += len(chosen)
            slots += min(3, len(batch))
            if dcg(ideal):
                ndcg.append(dcg(chosen) / dcg(ideal))
        result[name] = {"borrowable":useful, "slots":slots, "returned":returned, "precision_at_3":useful / slots if slots else None,
                        "ndcg_at_3":sum(ndcg) / len(ndcg) if ndcg else None, "ndcg_batches":len(ndcg)}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("samples", type=Path)
    parser.add_argument("--weights", help="当前后台权重 JSON；缺省用出厂默认值")
    parser.add_argument("--step", type=float, default=0.1, help="网格步长，默认 0.1")
    parser.add_argument("--output", type=Path, default=Path("ranking-calibration.json"))
    parser.add_argument("--split-key", default="split_group", help="整组留出的字段，默认 split_group 或 batch")
    parser.add_argument("--holdout-group", action="append", help="显式留出的分组值，可重复指定")
    args = parser.parse_args()
    if not (0.05 <= args.step <= 1 and math.isclose(1 / args.step, round(1 / args.step))):
        parser.error("步长须能整分 1，且不小于 0.05")
    current = json.loads(args.weights) if args.weights else DEFAULT
    all_rows, errors = load(args.samples, args.split_key)
    if errors:
        parser.error("样本解析失败：" + json.dumps(errors[:5], ensure_ascii=False))
    try:
        rows, held = partition(all_rows, args.holdout_group)
    except ValueError as exc:
        parser.error(str(exc))
    add_baselines(rows)
    add_baselines(held)
    labels = [r["label"] for r in rows]
    per_component = {}
    for key in KEYS:
        values = [ranking.score(r["content"], current)["components"].get(key) for r in rows]
        per_component[key] = {
            "auc": auc(values, labels),
            "coverage": sum(v is not None for v in values),
        }
    current_scores = [ranking.score(r["content"], current)["score"] for r in rows]
    best = grid(rows, args.step) if rows else None
    report = {
        "samples": len(all_rows),
        "train_samples": len(rows),
        "holdout_samples": len(held),
        "holdout_groups": sorted({r["split"] for r in held}),
        "overlap_excluded_from_training": len(all_rows) - len(rows) - len(held),
        "positives": sum(r["label"] for r in all_rows),
        "train_positives": sum(labels),
        "parse_errors": errors,
        "target_30_50_met": 30 <= len(all_rows) <= 50,
        "current_weights": current,
        "current_auc": auc(current_scores, labels),
        "per_component": per_component,
        "suggested_weights": best[1] if best else None,
        "suggested_auc": best[0] if best else None,
        "note": "AUC 0.5 等于随机，越接近 1 区分越好。样本少时建议权重容易过拟合，请结合业务判断再保存到后台。",
    }
    if held:
        versions = {"current": current}
        if best:
            versions["candidate"] = best[1]
        report["holdout"] = {
            "auc": {name:auc([ranking.score(r["content"], w)["score"] for r in held],
                             [r["label"] for r in held]) for name,w in versions.items()},
            "ranking": top_three(held, versions),
            "measured_records": sum(ranking.engagement(r["content"]) is not None for r in held),
            "scored_records": {name:sum(ranking.score(r["content"], w)["score"] is not None for r in held)
                               for name,w in versions.items()},
            "borrow_labels": sum(r["borrow"] is not None for r in held),
        }
    else:
        report["holdout"] = None
    report["note"] = "current_auc 与 suggested_auc 仅为训练集拟合。独立候选批次的表现见 holdout，缺少独立分组时无法验证升级。"
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "parse_errors"}, ensure_ascii=False, indent=2))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
