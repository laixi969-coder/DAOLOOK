"""Outcome selection, grounding, repetition and the real-results feedback loop."""
import copy
import csv
import io
import datetime
import json
import unittest
from unittest.mock import patch
from server import adapters, content_quality as quality, jobs
from tests import test_original as fixture


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.assets = [{"id": "product", "kind": "产品信息", "content": "冷萃挂耳每包12克，每盒10包。"}]
        self.output = {
            "title": "通勤咖啡怎么选", "body": "冷萃挂耳每包12克。你每天在哪喝咖啡？",
            "hook": "", "cover_text": "通勤怎么选", "titles": [], "tags": [], "missing": [],
            "audience": "通勤上班族", "value": "了解包装规格", "cta": "你每天在哪喝咖啡？",
            "evidence": [{"asset_id": "product", "quote": "冷萃挂耳每包12克"}],
        }

    def test_basic_checks_do_not_claim_to_verify_effect(self):
        result = quality.assess(self.output, self.assets, "xhs")
        self.assertEqual(result["status"], "checked")
        self.assertIn("仍需核对", result["note"])
        self.assertNotIn("score", result)

    def test_placeholders_in_public_fields_and_comments_are_flagged(self):
        for field in ("body", "hook", "title", "cover_text", "cta"):
            output = {**self.output, field: "购买入口 XX"}
            self.assertTrue(any("未填写" in x for x in quality.assess(output, self.assets, "xhs")["issues"]))
        output = {**self.output, "comment_layout": {"pinned": {"text": "到XX店购买"}}}
        self.assertEqual(quality.assess(output, self.assets, "xhs")["status"], "needs_input")

    def test_reference_or_unselected_evidence_cannot_pass(self):
        for evidence in ([{"asset_id": "reference", "quote": "冷萃挂耳每包12克"}],
                         [{"asset_id": "product", "quote": "一周卖出一万盒"}], []):
            output = {**self.output, "evidence": evidence}
            self.assertFalse(quality.evidence_valid(output, self.assets))
            self.assertEqual(quality.assess(output, self.assets, "xhs")["status"], "needs_input")
        self.assertFalse(quality.evidence_valid(self.output, [{**self.assets[0], "kind": "图片"}]))

    def test_cta_must_be_in_the_public_body(self):
        output = {**self.output, "cta": "在评论告诉我你需要几盒"}
        self.assertTrue(any("下一步" in x for x in quality.assess(output, self.assets, "xhs")["issues"]))

    def test_punctuation_only_duplicates_rejected(self):
        for field in ("title", "body"):
            outputs = adapters.demo_outputs("xhs", "冷萃", 1)
            outputs[1][field] = outputs[0][field] + " ！"
            with self.assertRaisesRegex(ValueError, "标点"):
                adapters.validate_creation({"outputs": outputs}, "xhs")

    def test_fabricated_citation_is_a_retryable_validation_error(self):
        outputs = adapters.demo_outputs("xhs", "冷萃", 1)
        outputs[0]["evidence"] = [{"asset_id": "product", "quote": "一周卖出一万盒"}]
        with self.assertRaisesRegex(ValueError, "原文"):
            adapters.validate_grounded_creation({"outputs": outputs}, "xhs", [], self.assets)

    def test_expired_temporary_cannot_be_reused_before_cleanup(self):
        old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)).isoformat()
        fresh = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.assertEqual(quality.reusable_temporary({"temporary": "资料"}, old, 24), "")
        self.assertEqual(quality.reusable_temporary({"temporary": "资料"}, fresh, 24), "资料")

    def test_results_keep_unknown_distinct_from_zero_and_reject_invalid(self):
        self.assertEqual(quality.clean_results({"leads": 0, "views": None}), {"leads": 0, "note": ""})
        for bad in ({"views": True}, {"leads": -1}, {"orders": 1.2}, {"spend": float("nan")}, {"spend": float("inf")}, {"views": "100"}, {"score": 99}):
            with self.assertRaises(ValueError):
                quality.clean_results(bad)

    def test_retry_receives_actionable_feedback(self):
        calls = []
        def request(*args):
            calls.append(copy.deepcopy(args[2]))
            return {"choices": [{"message": {"content": "{}"}}]}
        count = 0
        def validate(result):
            nonlocal count
            count += 1
            if count == 1:
                raise ValueError("事实引用必须来自本次资料")
        with patch.object(adapters, "candidates", return_value=[("test", {"base_url": "https://model.example", "api_key": "test"}, "test")]), patch.object(adapters, "setting", return_value={"retries": 1, "timeout": 1}), patch.object(adapters, "request_json", side_effect=request):
            adapters.model_json({}, {}, "旧提示词", "create", validate)
        self.assertEqual(len(calls), 2)
        self.assertIn("事实引用", calls[1]["messages"][-1]["content"])
        self.assertIn("业务事实只来自 assets", calls[0]["messages"][0]["content"])

    def test_both_generation_routes_receive_goal_and_real_feedback(self):
        seen = []
        history = [{"title": "选择咖啡", "results": {"leads": 3}}]
        def model(prompt, schema, version, kind, validator):
            seen.append(prompt)
            return {"outputs": adapters.demo_outputs("xhs", "冷萃", 1)}, "test"
        with patch.object(adapters, "model_json", side_effect=model):
            outputs, _ = adapters.create({"platform": "xhs", "title": "参考"}, self.assets, "", "", 1, goal="reach", history_results=history)
            original, _ = adapters.create_original({"platform": "xhs", "topic": "冷萃", "goal": "sales"}, {}, self.assets, "", "", 1, history_results=history)
        self.assertEqual(seen[0]["objective"]["goal"], "reach")
        self.assertEqual(seen[1]["objective"]["goal"], "sales")
        self.assertTrue(all(p["history_results"] == history for p in seen))
        self.assertTrue(all(o["goal"] == "reach" and "demo" not in o for o in outputs))
        self.assertTrue(all(o["goal"] == "sales" for o in original))


class OutcomeApiTests(unittest.TestCase):
    setUp = fixture.OriginalTests.setUp
    tearDown = fixture.OriginalTests.tearDown
    post = fixture.OriginalTests.post
    ws = fixture.OriginalTests.ws
    run_task = fixture.OriginalTests.run_task

    def generate(self, goal="sales"):
        status, r = self.post("/api/original", {"platform": "xhs", "topic": "冷萃咖啡", "temporary": "冷萃挂耳每包12克", "goal": goal})
        self.assertEqual(status, 202, r)
        self.run_task(r)
        return r

    def test_goal_and_temporary_survive_repeat(self):
        r = self.generate()
        status, repeat = self.post("/api/original", {"brief_id": r["brief_id"]})
        self.assertEqual(status, 202, repeat)
        self.run_task(repeat)
        self.assertEqual(len(self.ws()["creations"]), 16)
        self.assertTrue(all(c["data"]["goal"] == "sales" for c in self.ws()["creations"]))
        with fixture.D.db() as c:
            payload = json.loads(c.execute("SELECT payload FROM tasks WHERE id=?", (repeat["task_ids"][0],)).fetchone()[0])
        self.assertEqual(payload["temporary"], "冷萃挂耳每包12克")

    def test_invalid_goal_does_not_freeze_credits(self):
        balance = self.c.req("/api/bootstrap")[1]["credits"]
        for value in ("viral", [], None, 42):
            status, _ = self.post("/api/original", {"platform": "xhs", "topic": "咖啡", "temporary": "业务", "goal": value})
            self.assertEqual(status, 400)
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"], balance)

    def test_expired_repeat_fails_before_billing(self):
        r = self.generate()
        with fixture.D.db() as c:
            c.execute("UPDATE tasks SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (r["task_ids"][0],))
        balance = self.c.req("/api/bootstrap")[1]["credits"]
        self.assertEqual(self.post("/api/original", {"brief_id": r["brief_id"]})[0], 400)
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"], balance)

    def test_results_round_trip_isolation_and_history_scope(self):
        self.generate()
        creation = self.ws()["creations"][0]
        cid = creation["id"]
        status, _ = self.post("/api/results/" + cid, {"results": {"views": 200, "leads": 0, "orders": 2, "spend": 10.5}})
        self.assertEqual(status, 200)
        result = next(c for c in self.ws()["creations"] if c["id"] == cid)["results"]
        self.assertEqual(result["orders"], 2)
        self.assertEqual(result["leads"], 0)
        exported = self.c.req(f"/api/export?project_id={self.p}", raw=True)[1].decode("utf-8-sig")
        exported_row = next(r for r in csv.DictReader(io.StringIO(exported)) if r["稿件ID"] == cid)
        self.assertEqual(exported_row["有效咨询"], "0")
        self.assertEqual(exported_row["创作目标"], "更多人下单")
        self.assertEqual(exported_row["推广花费"], "10.5")
        self.assertEqual(jobs.history_results(self.p, "xhs", "sales"), [])  # Unpublished demo never informs generation.
        self.post("/api/tracking/" + cid, {"status": "published"})
        self.assertEqual(jobs.history_results(self.p, "xhs", "sales"), [])
        with fixture.D.db() as c:
            output = creation["data"]
            output.pop("demo")
            c.execute("UPDATE creation_outputs SET data=? WHERE id=?", (json.dumps(output), cid))
        self.assertEqual(len(jobs.history_results(self.p, "xhs", "sales")), 1)
        for project, platform, goal in ((self.p, "douyin", "sales"), (self.p, "xhs", "reach"), ("other", "xhs", "sales")):
            self.assertEqual(jobs.history_results(project, platform, goal), [])
        other = self.post("/api/projects", {"name": "另一个项目"})[1]["id"]
        status, _ = self.c.req("/api/results/" + cid, "POST", {"project_id": other, "results": {"orders": 9}})
        self.assertEqual(status, 404)
        self.c.req("/api/creations/" + cid, "DELETE", {"project_id": self.p})
        self.assertEqual(self.post("/api/results/" + cid, {"results": {"orders": 9}})[0], 404)
        self.assertEqual(jobs.history_results(self.p, "xhs", "sales"), [])

    def test_recreation_cannot_reinterpret_an_original_brief_as_reference(self):
        r = self.generate()
        self.assertEqual(self.post("/api/create", {"source_id": r["brief_id"]})[0], 400)

    def test_live_recreation_requires_own_material_before_billing(self):
        source = self.ws()["sources"][0]["id"]
        with fixture.D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        balance = self.c.req("/api/bootstrap")[1]["credits"]
        self.assertEqual(self.post("/api/create", {"source_id": source})[0], 400)
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"], balance)


if __name__ == "__main__":
    unittest.main()
