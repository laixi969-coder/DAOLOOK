"""用人工标注的真实样本校准「相对表现」排序权重（PRD 第 6 节、第 18 步）。

输入 JSONL，每行一条真实内容：
  {"platform": "xhs|douyin", "url": "...", "response": {TikHub 详情原始返回},
   "label": 1 或 0,                       # 1 = 你们认定的低粉高曝 / 异常爆款
   "group": "咖啡器具",                    # 可选：同赛道分组，用于计算赛道中位数
   "account_median": 1200,                # 可选：账号近期互动中位数（同口径）
   "reusability": 0.6}                    # 可选：0–1 人工可复用性打分

输出：每个维度单独的区分度（AUC）、当前权重的 AUC、网格搜索得到的建议权重。
不联网、不需要密钥；建议权重需人工确认后再到后台「内容排序权重」里保存。

  python3 scripts/calibrate_ranking.py samples.jsonl --weights '{"engagement":0.3,...}'
"""

import argparse, itertools, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.adapters import normalize
from server import ranking

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


def load(path):
    rows, errors = [], []
    for n, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            sample = json.loads(line)
            content = normalize(sample["response"], sample["platform"], sample.get("url", ""))
            for key in ("account_median", "category_median", "reusability"):
                if sample.get(key) is not None:
                    content[key] = sample[key]
            rows.append(
                {
                    "line": n,
                    "label": int(bool(sample["label"])),
                    "group": sample.get("group"),
                    "content": content,
                }
            )
        except Exception as e:
            errors.append({"line": n, "error": str(e)[:200]})
    groups = {}
    for r in rows:
        if r["group"]:
            groups.setdefault(r["group"], []).append(ranking.engagement(r["content"]))
    for r in rows:
        if r["group"] and r["content"].get("category_median") is None:
            r["content"]["category_median"] = ranking.median(groups[r["group"]])
    return rows, errors


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
        scores = []
        for c in comps:
            total = sum(weights[k] for k in c)
            scores.append(
                sum(v * weights[k] for k, v in c.items()) / total if total else None
            )
        value = auc(scores, labels)
        if value is not None and (best is None or value > best[0]):
            best = (value, weights)
    return best


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("samples", type=Path)
    parser.add_argument("--weights", help="当前后台权重 JSON；缺省用出厂默认值")
    parser.add_argument("--step", type=float, default=0.1, help="网格步长，默认 0.1")
    parser.add_argument("--output", type=Path, default=Path("ranking-calibration.json"))
    args = parser.parse_args()
    current = json.loads(args.weights) if args.weights else DEFAULT
    rows, errors = load(args.samples)
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
        "samples": len(rows),
        "positives": sum(labels),
        "parse_errors": errors,
        "target_30_50_met": 30 <= len(rows) <= 50,
        "current_weights": current,
        "current_auc": auc(current_scores, labels),
        "per_component": per_component,
        "suggested_weights": best[1] if best else None,
        "suggested_auc": best[0] if best else None,
        "note": "AUC 0.5 等于随机，越接近 1 区分越好。样本少时建议权重容易过拟合，请结合业务判断再保存到后台。",
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "parse_errors"}, ensure_ascii=False, indent=2))
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
