import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import blind_review as blind


class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name) / "review"
        self.cases = [
            {"id": str(i), "merchant": shop, "origin": "business", "input": {
                "topic": f"测试简报{i}", "platform": "xhs", "goal": "sales", "temporary": "售价199元。"}}
            for i, shop in enumerate(("shop-01", "shop-01", "shop-02", "shop-03"))]
        self.group = blind.split_cases(self.cases, 42, ["shop-01"])["holdout"]

    def arm(self, version):
        data = blind.response_template(self.group["cases"])
        data["version"] = version
        for row in data["records"]:
            row["draft"] = {"body": "首篇公开稿", "model": "隐藏此字段"}
        return data

    def filled(self, edit):
        sheet = self.out / "ratings.csv"
        with sheet.open(encoding="utf-8-sig", newline="") as fp:
            rows = list(csv.DictReader(fp))
        for row in rows:
            edit(row)
        with sheet.open("w", encoding="utf-8-sig", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=blind.COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        return sheet

    def test_merchant_split_is_disjoint_and_fixture_business_remain_separate(self):
        a = blind.split_cases(self.cases, 553)
        b = blind.split_cases(list(reversed(self.cases)), 553)
        def merchants(group):
            return {case["merchant"] for case in group["cases"]}
        self.assertEqual(merchants(a["holdout"]), merchants(b["holdout"]))
        self.assertTrue(merchants(a["holdout"]).isdisjoint(merchants(a["development"])))
        self.assertEqual(len(self.group["cases"]), 2)
        with self.assertRaisesRegex(ValueError, "分开"):
            blind.split_cases([*self.cases[:-1], {**self.cases[-1], "origin": "fixture"}], 1)
        with self.assertRaisesRegex(ValueError, "无效"):
            blind.split_cases([{**self.cases[0], "input": {"platform": "xhs", "goal": "unknown", "topic": "t"}}], 3)

    def test_mismatched_inputs_missing_records_and_unknown_failure_fail_closed(self):
        first = self.arm("baseline")
        second = self.arm("candidate")
        second["records"][0]["input_sha256"] = "different brief"
        with self.assertRaisesRegex(ValueError, "指纹"):
            blind.prepare(self.group, first, second, self.out)
        second["records"].pop(0)
        with self.assertRaisesRegex(ValueError, "所有简报"):
            blind.prepare(self.group, first, second, self.out)
        second = self.arm("candidate")
        second["records"][0]["draft"] = None
        with self.assertRaisesRegex(ValueError, "失败"):
            blind.prepare(self.group, first, second, self.out)
        self.assertFalse(self.out.exists())

    def test_ratings_cost_coverage_missing_and_retry_totals_do_not_leak_identity(self):
        a, b = self.arm("PRIVATE_VERSION_OLD"), self.arm("PRIVATE_VERSION_NEW")
        for row in a["records"]:
            row["usage"] = {"attempts": 2, "actual_usd": 0.15, "output_tokens": 12}
        b["records"][1].update(draft=None, failure="供应商未完成")
        b["records"][0]["usage"] = {"estimated_usd": 0.1, "attempts": 1}
        blind.prepare(self.group, a, b, self.out)
        for filename in ("ratings.csv", "review.txt"):
            content = (self.out / filename).read_text()
            for private in ("PRIVATE_VERSION", "shop-01", "隐藏此字段", "供应商未完成"):
                self.assertNotIn(private, content)
        key = blind.read(self.out / "private-key.json")
        blank = blind.report(key, self.out / "ratings.csv")
        self.assertEqual(blank["all_cases"]["baseline"]["reviewed"], 0)
        self.assertIsNone(blank["all_cases"]["baseline"]["publishable_rate_reviewed"])
        self.assertIsNone(blank["all_cases"]["baseline"]["actual_usd"]["per_publishable"])
        self.assertEqual(blank["both_outcomes_known"], 0)

        def mark(row):
            side = key["cases"][row["编号"]]["sides"][row["稿件"]]
            if not side["generated"]:
                return
            row.update(愿意发布="1", 首稿可确认="0", 编辑分钟="0", 事实错误数="0")
            if side["arm"] == "baseline":
                row["两稿偏好"] = row["稿件"]
            else:
                row.update(事实错误数="1", 事实问题="活动时间被改写", 编辑分钟="3.5", 实拍返工镜头="第2镜")
        scored = blind.report(key, self.filled(mark))
        self.assertEqual(scored["both_outcomes_known"], 2)
        self.assertEqual(scored["preferences"]["baseline"], 2)
        base, new = (scored["all_cases"][arm] for arm in blind.ARMS)
        self.assertEqual(base["actual_usd"]["per_publishable"], .15)
        self.assertEqual(base["attempts"]["known_total"], 4)
        self.assertEqual(base["edit_minutes_median"], 0)
        self.assertEqual(new["estimated_usd"]["coverage"], .5)
        self.assertIsNone(new["estimated_usd"]["per_publishable"])
        self.assertEqual(new["generation_failures"], 1)
        self.assertEqual(new["shoots_needing_rework"], 1)
        self.assertEqual(scored["editor_notes"][0]["reshoot"], "第2镜")

    def test_sheet_from_different_round_and_invalid_values_rejected(self):
        a, b = self.arm("before"), self.arm("after")
        blind.prepare(self.group, a, b, self.out)
        key = blind.read(self.out / "private-key.json")
        with self.assertRaisesRegex(ValueError, "已存在"):
            blind.prepare(self.group, a, b, self.out)
        sheet = self.filled(lambda row: row.update(愿意发布="1", 编辑分钟="NaN"))
        with self.assertRaisesRegex(ValueError, "非负"):
            blind.report(key, sheet)
        sheet = self.filled(lambda row: row.update(编号="from-other-round"))
        with self.assertRaisesRegex(ValueError, "轮次"):
            blind.report(key, sheet)

    def test_documented_cli_example_replays_archived_fixture(self):
        cli = [sys.executable, str(blind.ROOT / "scripts/blind_review.py")]
        subprocess.run([*cli, "example", str(self.out)], check=True, capture_output=True)
        result = subprocess.run([*cli, "report", str(self.out / "private-key.json"), str(self.out / "ratings.csv")],
                                check=True, capture_output=True)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["origin"], "fixture")
        self.assertEqual(summary["both_outcomes_known"], 0)
        self.assertIn("Open Desk Saturday", (self.out / "review.txt").read_text())

    def test_split_capture_prepare_and_score_using_recorded_inputs(self):
        archive = blind.ROOT / "docs/examples/open-desk-saturday.json"
        folder = self.out.parent
        item = {"id": "open", "merchant": "archive", "origin": "fixture", "input": blind.read(archive)["input"]}
        manifest = folder / "manifest.json"
        manifest.write_text(json.dumps([item]))
        cli = [sys.executable, str(blind.ROOT / "scripts/blind_review.py")]
        subprocess.run([*cli, "split", manifest, folder / "split", "--holdout-merchant", "archive"],
                       check=True, capture_output=True)
        group = folder / "split/holdout.json"
        for arm in blind.ARMS:
            subprocess.run([*cli, "capture", group, folder / (arm + ".json"), archive, "--version", arm],
                           check=True, capture_output=True)
        subprocess.run([*cli, "prepare", group, folder / "baseline.json", folder / "candidate.json", self.out],
                       check=True, capture_output=True)
        scored = blind.report(blind.read(self.out / "private-key.json"), self.out / "ratings.csv")
        self.assertEqual((scored["split"], scored["origin"], scored["cases"]), ("holdout", "fixture", 1))
        different = blind.read(archive)
        different["input"]["goal"] = "sales"
        mismatch = folder / "mismatch.json"
        mismatch.write_text(json.dumps(different))
        with self.assertRaisesRegex(ValueError, "原始简报"):
            blind.capture(blind.read(group), "test", [mismatch], folder / "bad.json")
        self.assertFalse((folder / "bad.json").exists())
