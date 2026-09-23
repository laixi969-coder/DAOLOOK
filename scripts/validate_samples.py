"""Offline validation of user-provided, real TikHub response samples.
JSONL rows: {"platform":"xhs|douyin", "url":"...", "response":{...}}
No network requests are performed and no credentials are required.
"""

import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.adapters import normalize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples", type=Path)
    parser.add_argument("--output", type=Path, default=Path("sample-validation.json"))
    args = parser.parse_args()
    rows = []
    for n, line in enumerate(args.samples.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            sample = json.loads(line)
            if sample["platform"] not in ("xhs", "douyin"):
                raise ValueError("unknown platform")
            content = normalize(
                sample["response"], sample["platform"], sample.get("url", "")
            )
            rows.append(
                {
                    "line": n,
                    "ok": True,
                    "title": content["title"],
                    "platform": content["platform"],
                    "missing_metrics": [
                        k
                        for k in ("likes", "saves", "comments", "followers")
                        if content.get(k) is None
                    ],
                }
            )
        except Exception as error:
            rows.append({"line": n, "ok": False, "error": str(error)})
    report = {
        "sample_count": len(rows),
        "passed": sum(r["ok"] for r in rows),
        "real_sample_target_met": 30 <= len(rows) <= 50,
        "scope": "Only extraction and field coverage; does not verify model quality or calibrate ranking.",
        "results": rows,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "results"}, ensure_ascii=False
        )
    )
    return 0 if rows and all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
