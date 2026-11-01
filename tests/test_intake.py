"""单问题追问（内容效果升级·第一优先）：确定性规则、一次一问、回答并入临时资料。"""

import importlib, json, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

D = importlib.import_module("server.db")
from server import app, jobs, intake
from tests.test_app import Client


class IntakeRuleTests(unittest.TestCase):
    def test_no_materials_never_asks(self):
        self.assertIsNone(intake.blocking_question("sales", [], ""))
        self.assertIsNone(intake.blocking_question("leads", [], "   "))
        # reach 目标不设缺口问题
        self.assertIsNone(intake.blocking_question("reach", [{"content": "随便写写"}], ""))

    def test_sales_without_price_or_purchase(self):
        q = intake.blocking_question("sales", [{"content": "冷萃挂耳，每盒10包"}], "")
        self.assertEqual(q["id"], "sales_missing")

    def test_sales_with_purchase_path_ok(self):
        self.assertIsNone(intake.blocking_question("sales", [{"content": "扫码进小店下单"}], ""))

    def test_leads_without_contact(self):
        q = intake.blocking_question("leads", [{"content": "冷萃挂耳，每盒10包"}], "")
        self.assertEqual(q["id"], "leads_missing")

    def test_leads_with_contact_ok(self):
        self.assertIsNone(intake.blocking_question("leads", [{"content": "加微信 coffee888"}], ""))

    def test_price_conflict_wins_and_lists_prices(self):
        q = intake.blocking_question("leads", [{"content": "零售 12 元，活动 9.9 元"}], "")
        self.assertEqual(q["id"], "price_conflict")
        self.assertIn("9.9", q["question"])
        self.assertIn("12", q["question"])

    def test_temporary_counts_as_material(self):
        self.assertIsNone(intake.blocking_question("leads", [], "私信我咨询"))
        # 图片资料没有文字内容，不参与判断
        q = intake.blocking_question("leads", [{"content": ""}], "冷萃")
        self.assertEqual(q["id"], "leads_missing")

    def test_apply_answer_merges_into_temporary(self):
        payload = {"temporary": "已有资料"}
        intake.apply_answer(payload, "sales_missing", "128 元，抖音小店下单")
        self.assertIn("已有资料", payload["temporary"])
        self.assertIn("用户补充回答（sales_missing）：128 元，抖音小店下单", payload["temporary"])

    def test_apply_answer_validates_length_and_emptiness(self):
        with self.assertRaises(ValueError):
            intake.apply_answer({"temporary": ""}, "x", "   ")
        with self.assertRaises(ValueError):
            intake.apply_answer({"temporary": ""}, "x", "字" * 501)


class IntakeApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / "db.sqlite")
        D.init()
        app.RATE.clear()
        self.queue = patch.object(jobs.Q, "put")
        self.queue.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.c = Client(f"http://127.0.0.1:{self.server.server_address[1]}")
        self.c.req("/api/auth/demo", "POST", {})
        self.p = self.c.req("/api/bootstrap")[1]["projects"][0]["id"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.queue.stop()
        D.DB_PATH = self.original
        self.temp.cleanup()

    def post(self, path, data):
        return self.c.req(path, "POST", {"project_id": self.p, **data})

    def saved_source(self):
        sid = D.uid()
        with D.db() as c:
            c.execute(
                "INSERT INTO source_contents VALUES (?,?,?,?,?,?,?)",
                (sid, self.p, "xhs", "https://x.example/note", D.dumps({"platform": "xhs", "title": "参考笔记", "likes": 10, "url": "https://x.example/note"}), 1, D.now()),
            )
        return sid

    def test_create_asks_once_then_merges_answer(self):
        sid = self.saved_source()
        status, r = self.post("/api/create", {"source_id": sid, "assets": [], "temporary": "冷萃挂耳", "goal": "leads"})
        self.assertEqual(status, 200)
        self.assertEqual(r["ask"]["id"], "leads_missing")
        self.assertNotIn("task_ids", r)
        status, r = self.post("/api/create", {"source_id": sid, "assets": [], "temporary": "冷萃挂耳", "goal": "leads", "answer": "私信我咨询"})
        self.assertEqual(status, 202)
        jobs.run(r["task_ids"][0])
        with D.db() as c:
            payload = json.loads(c.execute("SELECT payload FROM tasks WHERE id=?", (r["task_ids"][0],)).fetchone()["payload"])
        self.assertIn("用户补充回答（leads_missing）：私信我咨询", payload["temporary"])
        # 明确跳过：不再追问，直接入队
        status, r2 = self.post("/api/create", {"source_id": sid, "assets": [], "temporary": "冷萃挂耳", "goal": "leads", "skip_question": True})
        self.assertEqual(status, 202)

    def test_create_with_sufficient_materials_skips_question(self):
        sid = self.saved_source()
        status, r = self.post("/api/create", {"source_id": sid, "assets": [], "temporary": "冷萃挂耳 12 元，私信咨询", "goal": "sales"})
        self.assertEqual(status, 202)
        self.assertIn("task_ids", r)

    def test_create_rejects_overlong_answer(self):
        sid = self.saved_source()
        status, _ = self.post("/api/create", {"source_id": sid, "assets": [], "temporary": "冷萃挂耳", "goal": "leads", "answer": "字" * 501})
        self.assertEqual(status, 400)

    def test_original_asks_domestic_and_merges_answer(self):
        status, r = self.post("/api/original", {"platform": "xhs", "topic": "冷萃挂耳", "temporary": "冷萃挂耳", "goal": "sales"})
        self.assertEqual(status, 200)
        self.assertEqual(r["ask"]["id"], "sales_missing")
        status, r = self.post("/api/original", {"platform": "xhs", "topic": "冷萃挂耳", "temporary": "冷萃挂耳", "goal": "sales", "answer": "128 元，抖音小店下单"})
        self.assertEqual(status, 202)
        jobs.run(r["task_ids"][0])
        with D.db() as c:
            payload = json.loads(c.execute("SELECT payload FROM tasks WHERE id=?", (r["task_ids"][0],)).fetchone()["payload"])
        self.assertIn("128 元，抖音小店下单", payload["temporary"])

    def test_original_overseas_platforms_do_not_ask(self):
        status, r = self.post("/api/original", {"platform": "tiktok", "topic": "cold brew", "temporary": "cold brew", "goal": "sales"})
        self.assertEqual(status, 202)
        self.assertIn("task_ids", r)


if __name__ == "__main__":
    unittest.main()
