"""AI 单条定向重写（内容效果升级·第一优先）：新版本追加、乐观锁、计费与退款。"""

import importlib, json, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

D = importlib.import_module("server.db")
from server import app, jobs, adapters
from tests.test_app import Client


class RewriteTests(unittest.TestCase):
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

    def ws(self):
        return self.c.req(f"/api/workspace?project_id={self.p}")[1]

    def credits(self):
        return self.c.req("/api/bootstrap")[1]["credits"]["balance"]

    def make_draft(self, platform="xhs"):
        status, r = self.post(
            "/api/original",
            {"platform": platform, "topic": "冷萃挂耳", "temporary": "冷萃挂耳每包12克，私信咨询", "skip_question": True},
        )
        self.assertEqual(status, 202, r)
        jobs.run(r["task_ids"][0])
        return self.ws()["creations"][0]["id"]

    def test_skills_and_default_rule(self):
        with D.db() as c:
            names = {r[0] for r in c.execute("SELECT name FROM skill_versions WHERE status='Published'")}
        self.assertTrue({"xhs_rewrite", "douyin_rewrite"} <= names)
        self.assertEqual(jobs.task_cost("rewrite", {}), (3, 3))

    def test_demo_rewrite_appends_revision_and_charges(self):
        cid = self.make_draft()
        before = self.credits()
        status, r = self.post(f"/api/creations/{cid}/rewrite", {"revision": 0, "instruction": "开头换成加班场景"})
        self.assertEqual(status, 202, r)
        jobs.run(r["task_ids"][0])
        with D.db() as c:
            task = dict(c.execute("SELECT * FROM tasks WHERE id=?", (r["task_ids"][0],)).fetchone())
        self.assertEqual(task["state"], "SUCCEEDED", task)
        self.assertEqual(task["cost"], 3)
        self.assertEqual(self.credits(), before - 3)
        creation = next(x for x in self.ws()["creations"] if x["id"] == cid)
        self.assertIn("演示重写", creation["data"]["body"])
        self.assertEqual(creation["revision"], 1)
        history = self.c.req(f"/api/creations/{cid}/revisions?project_id={self.p}")[1]
        reasons = [h["reason"] for h in history]
        self.assertIn("初始稿", reasons)
        self.assertIn("AI 定向重写", reasons)
        self.assertEqual(json.loads(task["result"])["revision"], 1)

    def test_guards(self):
        cid = self.make_draft()
        self.assertEqual(self.post(f"/api/creations/{cid}/rewrite", {"revision": 0, "instruction": "改"})[0], 400)
        self.assertEqual(self.post(f"/api/creations/{cid}/rewrite", {"instruction": "改成送礼场景"})[0], 400)
        self.assertEqual(self.post(f"/api/creations/{cid}/rewrite", {"revision": 5, "instruction": "改成送礼场景"})[0], 409)
        self.assertEqual(self.post("/api/creations/" + "f" * 32 + "/rewrite", {"revision": 0, "instruction": "改成送礼场景"})[0], 404)
        # 已发布稿件保留原文
        self.post(f"/api/tracking/{cid}", {"status": "published"})
        self.assertEqual(self.post(f"/api/creations/{cid}/rewrite", {"revision": 0, "instruction": "改成送礼场景"})[0], 409)
        # 海外稿件不在本期内
        overseas = self.make_draft(platform="tiktok")
        self.assertEqual(self.post(f"/api/creations/{overseas}/rewrite", {"revision": 0, "instruction": "改成送礼场景"})[0], 400)

    def test_edit_during_execution_fails_and_refunds(self):
        cid = self.make_draft()
        before = self.credits()
        status, r = self.post(f"/api/creations/{cid}/rewrite", {"revision": 0, "instruction": "开头换成加班场景"})
        self.assertEqual(status, 202)
        # 重写排队期间稿件被手动编辑到版本 1
        status, _ = self.post(f"/api/creations/{cid}/edit", {"revision": 0, "changes": {"title": "手动改过的标题"}})
        self.assertEqual(status, 200)
        with patch.object(adapters, "model_json", side_effect=AssertionError("不应调用模型")):
            try:
                jobs.run(r["task_ids"][0])
            except ValueError as e:
                jobs.fail(r["task_ids"][0], str(e))
        with D.db() as c:
            task = dict(c.execute("SELECT state FROM tasks WHERE id=?", (r["task_ids"][0],)).fetchone())
        self.assertEqual(task["state"], "FAILED")
        self.assertEqual(self.credits(), before)
        creation = next(x for x in self.ws()["creations"] if x["id"] == cid)
        self.assertEqual(creation["data"]["title"], "手动改过的标题")
        self.assertEqual(creation["revision"], 1)

    def test_live_model_rewrite(self):
        user = app.new_user("formal@rewrite.test", "test-password-123")
        self.c.req("/api/auth/login", "POST", {"email": "formal@rewrite.test", "password": "test-password-123"})
        self.p = self.c.req("/api/bootstrap")[1]["projects"][0]["id"]
        from server import access
        admin = app.new_user("admin@rewrite.test", "test-admin-password", "admin")
        with D.db() as c:
            c.execute("BEGIN IMMEDIATE")
            access.approve(c, user, admin, "test_admin", preserve_balance=True)
        cid = self.make_draft()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        seen = []

        def fake(prompt, schema, version, kind="analyze", validator=None):
            seen.append(json.loads(json.dumps(prompt)))
            draft = json.loads(json.dumps(prompt["draft"]))
            draft["body"] = "改写后的正文：开头换成加班场景。" + draft["body"][:20]
            result = {"output": draft}
            if validator:
                validator(result)
            return result, "fake/model"

        with patch.object(adapters, "model_json", side_effect=fake):
            status, r = self.post(f"/api/creations/{cid}/rewrite", {"revision": 0, "instruction": "开头换成加班场景"})
            self.assertEqual(status, 202, r)
            jobs.run(r["task_ids"][0])
        self.assertEqual(seen[0]["instruction"], "开头换成加班场景")
        self.assertTrue(seen[0]["draft"]["title"])
        creation = next(x for x in self.ws()["creations"] if x["id"] == cid)
        self.assertIn("改写后的正文", creation["data"]["body"])
        self.assertEqual(creation["revision"], 1)

    def test_validate_rewrite(self):
        good = adapters.demo_outputs("xhs", "冷萃", 1)[0]
        adapters.validate_rewrite({"output": good}, "xhs")
        with self.assertRaises(ValueError):
            adapters.validate_rewrite({"output": {**good, "direction": "随想"}}, "xhs")
        with self.assertRaises(ValueError):
            adapters.validate_rewrite({"output": {**good, "title": "  "}}, "xhs")
        with self.assertRaises(ValueError):
            adapters.validate_rewrite({}, "xhs")


if __name__ == "__main__":
    unittest.main()
