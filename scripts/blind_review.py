"""Prepare and score paired editorial reviews without contacting a model or changing the workspace."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import secrets
import statistics
import tempfile


ROOT = Path(__file__).resolve().parents[1]
ARMS = ("baseline", "candidate")
LABELS = ("A", "B")
COLUMNS = ["编号", "稿件", "愿意发布", "首稿可确认", "编辑分钟", "事实错误数", "事实问题", "实拍返工镜头", "两稿偏好"]
PUBLIC_FIELDS = {
    "title": "标题", "titles": "备选标题", "cover_text": "封面文字", "hook": "开头", "body": "正文",
    "tags": "话题", "cta": "行动引导", "script": "口播", "translation_zh": "中文翻译",
    "image_suggestions": "配图", "storyboard": "分镜", "shooting_list": "拍摄清单", "shots": "拍摄方案",
    "shoot_setup": "拍摄准备", "comments": "评论", "comment_layout": "评论安排", "missing": "待补资料",
}
USAGE = ("attempts", "input_tokens", "output_tokens", "actual_usd", "estimated_usd")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def write_new_directory(destination, build):
    destination = Path(destination)
    if destination.exists():
        raise ValueError(f"输出目录已存在，请指定新目录：{destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
        stage = Path(temp) / "run"
        stage.mkdir(mode=0o700)
        build(stage)
        os.rename(stage, destination)


def digest(brief):
    encoded = json.dumps(brief, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def text_field(record, field):
    value = record.get(field) if isinstance(record, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"请填写 {field}")
    return value


def split_cases(cases, seed, holdout_merchants=None):
    if not isinstance(cases, list) or not cases:
        raise ValueError("简报列表为空")
    merchants, ids, origins = set(), set(), set()
    inputs = []
    for case in cases:
        ident, merchant = text_field(case, "id"), text_field(case, "merchant")
        origin = text_field(case, "origin")
        if origin not in ("business", "fixture") or ident in ids:
            raise ValueError(f"{ident} 的 origin 无效或编号重复")
        brief = case.get("input")
        text_field(brief, "topic")
        if brief.get("platform") not in ("xhs", "douyin", "overseas", "tiktok", "instagram", "youtube"):
            raise ValueError(f"{ident} 的 platform 无效")
        if brief.get("goal") not in ("reach", "leads", "sales"):
            raise ValueError(f"{ident} 的 goal 无效")
        ids.add(ident)
        merchants.add(merchant)
        origins.add(origin)
        inputs.append(dict(id=ident, merchant=merchant, input=brief, input_sha256=digest(brief)))
    if len(origins) != 1:
        raise ValueError("真实业务简报与回放样例请分开评测")
    if holdout_merchants is None:
        ordered = sorted(merchants)
        random.Random(seed).shuffle(ordered)
        size = max(1, round(len(ordered) * .25)) if len(ordered) > 1 else 0
        holdout_merchants = set(ordered[:size])
    else:
        holdout_merchants = set(holdout_merchants)
        if holdout_merchants - merchants:
            raise ValueError("指定的留出商家缺少对应简报")
    return {
        group: {"split": group, "origin": next(iter(origins)), "cases": [
            c for c in inputs if (c["merchant"] in holdout_merchants) == (group == "holdout")
        ]} for group in ("development", "holdout")
    }


def response_template(cases):
    return {"version": "", "records": [
        {"id": c["id"], "input_sha256": c["input_sha256"], "draft": None, "failure": None,
         "usage": dict.fromkeys(USAGE)} for c in cases
    ]}


def split_files(manifest, output, seed, holdout):
    groups = split_cases(read(manifest), seed, holdout)

    def build(folder):
        for name, group in groups.items():
            (folder / f"{name}.json").write_text(dump(group), encoding="utf-8")
            template = response_template(group["cases"])
            (folder / f"{name}.responses.json").write_text(dump(template), encoding="utf-8")

    write_new_directory(output, build)


def public_draft(draft):
    if isinstance(draft, str):
        value = draft.strip()
    elif isinstance(draft, dict):
        parts = []
        for field, label in PUBLIC_FIELDS.items():
            content = draft.get(field)
            if content:
                parts.append(label + "\n" + (content if isinstance(content, str) else dump(content)))
        value = "\n\n".join(parts)
    else:
        value = ""
    if not value:
        raise ValueError("请提供可供编辑阅读的成品文案，生成失败请填写 failure")
    return value


def checked_usage(value):
    if not isinstance(value, dict) or set(value) - set(USAGE):
        raise ValueError("usage 费用或用量字段无效")
    for key, number in value.items():
        if number is None:
            continue
        if key.endswith("_usd"):
            good = type(number) in (float, int) and math.isfinite(number)
        else:
            good = type(number) is int
        if not good or number < 0:
            raise ValueError(f"{key} 必须是非负数，未观测值填 null")
    return value


def indexed_responses(payload, expected):
    version = text_field(payload, "version")
    rows = payload.get("records")
    if not isinstance(rows, list):
        raise ValueError("版本回放文件缺少 records")
    results = {}
    for row in rows:
        ident = text_field(row, "id")
        if ident not in expected or ident in results or row.get("input_sha256") != expected[ident]:
            raise ValueError(f"回放记录 {ident} 的编号或输入指纹不匹配")
        failure = row.get("failure")
        if failure is not None and (not isinstance(failure, str) or not failure.strip() or row.get("draft") is not None):
            raise ValueError(f"{ident} 应提供一份成品文案或明确失败原因")
        results[ident] = {"draft": public_draft(row.get("draft")) if failure is None else None,
                          "usage": checked_usage(row.get("usage", {}))}
    if results.keys() != expected.keys():
        raise ValueError("每个版本均需覆盖所有简报，失败也应单独登记")
    return version, results


def capture(group, version, files, output):
    """Bind archived Daolook batches to cases using the original recorded input."""
    expected = {c["id"]: digest(c["input"]) for c in group["cases"]}
    records = []
    for path in files:
        batch = read(path)
        hashed = digest(batch["input"])
        matches = [ident for ident, value in expected.items() if hashed == value]
        ident = batch.get("id")
        if ident is None and len(matches) == 1:
            ident = matches[0]
        if ident not in matches:
            raise ValueError(f"{path.name} 的原始简报不匹配或对应多个样本，请核对 id 和 input")
        outputs = batch.get("outputs")
        if outputs is not None and not isinstance(outputs, list):
            raise ValueError(f"{path.name} 的 outputs 应为数组")
        records.append({"id": ident, "input_sha256": hashed,
                        "draft": outputs[0] if outputs else None, "failure": batch.get("failure"),
                        "usage": batch.get("usage", {})})
    payload = {"version": version, "records": records}
    indexed_responses(payload, expected)
    with output.open("x", encoding="utf-8") as fp:
        fp.write(dump(payload))


def prepare(group, baseline, candidate, out):
    if group.get("split") not in ("development", "holdout") or group.get("origin") not in ("business", "fixture"):
        raise ValueError("需要 split 产出的简报文件")
    cases = group.get("cases")
    if not cases:
        raise ValueError("这组没有简报")
    expected = {c["id"]: digest(c["input"]) for c in cases}
    if len(expected) != len(cases) or any(c.get("input_sha256") != expected[c["id"]] for c in cases):
        raise ValueError("简报输入已修改，需重新分组和生成")
    versions, by_arm = {}, {}
    for arm, payload in zip(ARMS, (baseline, candidate)):
        versions[arm], by_arm[arm] = indexed_responses(payload, expected)
    if versions["baseline"] == versions["candidate"]:
        raise ValueError("请分别标注现版和候选版版本或运行标识")

    def build(folder):
        cases_ordered = list(cases)
        rng = secrets.SystemRandom()
        rng.shuffle(cases_ordered)
        book, blanks, key_cases = [], [], {}
        for case in cases_ordered:
            blind_id = secrets.token_hex(6)
            arms = list(ARMS)
            rng.shuffle(arms)
            book.append(f"编号 {blind_id}\n\n业务简报\n{dump(case['input'])}")
            sides = {}
            for label, arm in zip(LABELS, arms):
                row = by_arm[arm][case["id"]]
                sides[label] = {"arm": arm, "generated": row["draft"] is not None, "usage": row["usage"]}
                copy = row["draft"] or "本轮未交付稿件"
                book.append(f"稿件 {label}\n{copy}")
                blanks.append([blind_id, label] + [""] * (len(COLUMNS) - 2))
            key_cases[blind_id] = {"id": case["id"], "merchant": case["merchant"],
                                   "platform": case["input"]["platform"], "goal": case["input"]["goal"], "sides": sides}
        key = {"split": group["split"], "origin": group["origin"], "versions": versions, "cases": key_cases}
        (folder / "private-key.json").write_text(dump(key), encoding="utf-8")
        (folder / "review.txt").write_text("\n\n".join(book) + "\n", encoding="utf-8")
        with (folder / "ratings.csv").open("w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.writer(fp)
            writer.writerow(COLUMNS)
            writer.writerows(blanks)

    write_new_directory(out, build)


def rating_number(value, label, integer=False):
    if not value:
        return None
    try:
        number = int(value) if integer else float(value)
    except ValueError:
        raise ValueError(f"{label} 需要填写非负数字") from None
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} 需要填写非负数字")
    return number


def parse_rating(row, generated):
    flags = {name: row[name] for name in ("愿意发布", "首稿可确认")}
    if any(v not in ("", "0", "1") for v in flags.values()):
        raise ValueError("愿意发布、首稿可确认请填写 0 或 1")
    minutes = rating_number(row["编辑分钟"], "编辑分钟")
    errors = rating_number(row["事实错误数"], "事实错误数", integer=True)
    shot = row["实拍返工镜头"]
    if not generated and any(row[f] for f in COLUMNS[2:-1]):
        raise ValueError("生成失败的稿件评分栏应留空")
    if flags["首稿可确认"] == "1" and flags["愿意发布"] != "1":
        raise ValueError("首稿可确认时，愿意发布应为 1")
    if not flags["愿意发布"] and any(row[f] for f in COLUMNS[3:-1]):
        raise ValueError("已填写评语的稿件还需要填写愿意发布")
    if row["事实问题"] and errors in (None, 0):
        raise ValueError("填写事实问题时应同时记录错误数")
    return {"publish": int(flags["愿意发布"]) if flags["愿意发布"] else None,
            "first": int(flags["首稿可确认"]) if flags["首稿可确认"] else None,
            "minutes": minutes, "errors": errors, "issue": row["事实问题"],
            "shoot_rework": shot or None}


def ratio(numerator, denominator):
    return round(numerator / denominator, 5) if denominator else None


def summarize(rows):
    n = len(rows)
    generated = sum(r["generated"] for r in rows)
    publish = [r["publish"] for r in rows if r["publish"] is not None]
    first = [r["first"] for r in rows if r["first"] is not None]
    minutes = [r["minutes"] for r in rows if r["minutes"] is not None]
    errors = [r["errors"] for r in rows if r["errors"] is not None]
    shoots = [r["shoot_rework"] for r in rows if r["shoot_rework"] is not None]
    metrics = {"submitted": n, "generation_failures": n - generated,
               "reviewed": len(publish), "review_coverage_of_generated": ratio(len(publish), generated),
               "publishable": sum(publish), "publishable_rate_reviewed": ratio(sum(publish), len(publish)),
               "publishable_per_submitted": ratio(sum(publish), n) if len(publish) == generated else None,
               "first_pass_recorded": len(first), "first_pass_confirmed": sum(first),
               "first_pass_confirmed_per_submitted": ratio(sum(first), n) if len(first) == generated else None,
               "edit_minutes_recorded": len(minutes), "edit_minutes_median": statistics.median(minutes) if minutes else None,
               "fact_checks_recorded": len(errors), "fact_errors": sum(errors) if errors else None,
               "shoots_recorded": len(shoots), "shoots_needing_rework": sum(s != "无" for s in shoots) if shoots else None}
    for field in USAGE:
        values = [r["usage"][field] for r in rows if r["usage"].get(field) is not None]
        metrics[field] = {"recorded": len(values), "coverage": ratio(len(values), n),
                          "known_total": round(sum(values), 6) if values else None}
        if field == "attempts":
            metrics[field]["known_retries"] = sum(max(0, count - 1) for count in values) if values else None
        if field.endswith("_usd"):
            metrics[field]["per_publishable"] = (
                ratio(sum(values), sum(publish)) if len(values) == n and len(publish) == generated else None
            )
    return metrics


def report(key, sheet):
    cases = key["cases"]
    expected = {(ident, side) for ident in cases for side in LABELS}
    ratings, votes = {}, {}
    with Path(sheet).open(encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames != COLUMNS:
            raise ValueError("评分表列名与生成的模板不一致")
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"第 {reader.line_num} 行列数错误")
            row = {k: v.strip() for k, v in row.items()}
            ident, label = row["编号"], row["稿件"]
            if (ident, label) not in expected or (ident, label) in ratings:
                raise ValueError(f"第 {reader.line_num} 行编号或稿件代号无效、重复或属于其他轮次")
            side = cases[ident]["sides"][label]
            ratings[ident, label] = {**side, **parse_rating(row, side["generated"])}
            vote = row["两稿偏好"]
            if vote:
                if vote not in ("A", "B", "相当", "均不选") or votes.get(ident, vote) != vote:
                    raise ValueError(f"{ident} 的两稿偏好无效或不一致")
                votes[ident] = vote
    if ratings.keys() != expected:
        raise ValueError("评分表缺少行，未评的稿件请保留空行")
    for ident, vote in votes.items():
        if vote in LABELS and not ratings[ident, vote]["generated"]:
            raise ValueError(f"{ident} 不能选择未生成的稿件")
    pairs = {ident for ident in cases if all(
        not ratings[ident, s]["generated"] or ratings[ident, s]["publish"] is not None for s in LABELS
    )}
    paired = {}
    by_arm = {}
    comments = []
    for arm in ARMS:
        all_rows = [v for v in ratings.values() if v["arm"] == arm]
        by_arm[arm] = summarize(all_rows)
        paired[arm] = summarize([r for (i, _), r in ratings.items() if i in pairs and r["arm"] == arm])
    for (i, _), r in ratings.items():
        if r["issue"] or r["shoot_rework"] not in ("无", None):
            comments.append({"id": cases[i]["id"], "arm": r["arm"], "fact_issue": r["issue"],
                             "reshoot": r["shoot_rework"]})
    preferences = dict.fromkeys((*ARMS, "相当", "均不选"), 0)
    for i, vote in votes.items():
        preferences[cases[i]["sides"][vote]["arm"] if vote in LABELS else vote] += 1
    distribution = {}
    for case in cases.values():
        goals = distribution.setdefault(case["platform"], {})
        goals[case["goal"]] = goals.get(case["goal"], 0) + 1
    return {"split": key["split"], "origin": key["origin"], "versions": key["versions"],
            "merchants": len({c["merchant"] for c in cases.values()}), "cases": len(cases),
            "briefs_by_platform_and_goal": distribution,
            "both_outcomes_known": len(pairs), "complete_pairs": paired, "all_cases": by_arm,
            "preferences_recorded": len(votes), "preferences": preferences, "editor_notes": comments}


def example(out):
    archived = read(ROOT / "docs/examples/open-desk-saturday.json")
    group = split_cases([{"id": "open-desk", "merchant": "fixture-harbor", "origin": "fixture",
                          "input": archived["input"]}], 0)["development"]
    recorded = response_template(group["cases"])
    recorded["records"][0]["draft"] = archived["outputs"][0]
    prepare(group, {**recorded, "version": "归档输出回放 1"},
            {**recorded, "version": "归档输出回放 2（同一稿）"}, out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(required=True, dest="action")
    split = sub.add_parser("split", help="按商家分组，生成输入快照和两版共用的回放模板")
    split.add_argument("manifest", type=Path)
    split.add_argument("output", type=Path)
    split.add_argument("--seed", type=int, default=41)
    split.add_argument("--holdout-merchant", action="append")
    snapshots = sub.add_parser("capture", help="按原始输入指纹读取已生成的 Daolook 批次首稿")
    snapshots.add_argument("group", type=Path)
    snapshots.add_argument("output", type=Path)
    snapshots.add_argument("batches", nargs="+", type=Path)
    snapshots.add_argument("--version", required=True)
    pack = sub.add_parser("prepare", help="按相同输入配对固定输出并生成匿名评审包")
    for field in ("group", "baseline", "candidate", "output"):
        pack.add_argument(field, type=Path)
    review = sub.add_parser("report", help="读取评分表，在终端输出 JSON 报告")
    review.add_argument("key", type=Path)
    review.add_argument("ratings", type=Path)
    sub.add_parser("example", help="以仓库已有海外简报做同稿回放").add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "split":
            split_files(args.manifest, args.output, args.seed, args.holdout_merchant)
        elif args.action == "capture":
            capture(read(args.group), args.version, args.batches, args.output)
        elif args.action == "prepare":
            prepare(read(args.group), read(args.baseline), read(args.candidate), args.output)
        elif args.action == "report":
            print(dump(report(read(args.key), args.ratings)))
        else:
            example(args.output)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        parser.exit(2, f"盲评输入错误：{exc}\n")


if __name__ == "__main__":
    main()
