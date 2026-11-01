"""资料结构化入库（内容效果升级·第一优先）：自动整理、出处校验、重整替换、创作引用、免费。"""

import importlib, json, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

D = importlib.import_module("server.db")
from server import app, jobs, adapters
from tests.test_app import Client

PRODUCT = "山野咖啡冷萃挂耳，12 克一包，售价 45 元，私信咨询。"


class AssetFactsTests(unittest.TestCase):
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

    def latest_facts_task(self):
        with D.db() as c:
            row = c.execute(
                "SELECT id FROM tasks WHERE project_id=? AND kind='facts' ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (self.p,),
            ).fetchone()
        return row["id"] if row else None

    def test_default_rules_and_free_task(self):
        rules = D.setting("rules")
        self.assertEqual(rules["rewrite"], 3)
        self.assertEqual(rules["facts"], 0)
        self.assertEqual(jobs.task_cost("facts", {}), (0, 0))
        self.assertEqual(jobs.task_cost("facts", {}, {"facts": 2}), (2, 2))

    def test_save_text_asset_auto_queues_free_extraction(self):
        before = self.c.req("/api/bootstrap")[1]["credits"]["balance"]
        status, asset = self.post("/api/assets", {"name": "产品", "kind": "产品信息", "content": PRODUCT})
        self.assertEqual(status, 200)
        task_id = self.latest_facts_task()
        self.assertTrue(task_id)
        jobs.run(task_id)
        with D.db() as c:
            task = dict(c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
            freezes = c.execute(
                "SELECT count(*) FROM credit_ledger WHERE task_id=? AND kind='FREEZE'", (task_id,)
            ).fetchone()[0]
        self.assertEqual(task["state"], "SUCCEEDED")
        self.assertEqual(task["cost"], 0)
        self.assertEqual(freezes, 0)
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], before)
        facts = next(a for a in self.ws()["assets"] if a["id"] == asset["id"])["facts"]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["category"], "卖什么")
        self.assertIn(facts[0]["quote"], PRODUCT)
        self.assertTrue(facts[0]["demo"])

    def test_refine_replaces_rows_and_live_model_path(self):
        self.formal_account()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        # 真实模式未配置模型：自动整理不排队
        status, asset = self.post("/api/assets", {"name": "产品", "kind": "产品信息", "content": PRODUCT})
        self.assertEqual(status, 200)
        self.assertIsNone(self.latest_facts_task())

        def fake(prompt, schema, version, kind="analyze", validator=None):
            result = {
                "facts": [
                    {"category": "卖什么", "fact": "冷萃挂耳 12 克一包", "quote": "12 克一包"},
                    {"category": "购买路径", "fact": "私信咨询后下单", "quote": "私信咨询"},
                ]
            }
            if validator:
                validator(result)
            return result, "fake/model"

        with patch.object(adapters, "model_json", side_effect=fake):
            status, r = self.post(f"/api/assets/{asset['id']}/facts", {})
            self.assertEqual(status, 202, r)
            jobs.run(r["task_ids"][0])
        facts = next(a for a in self.ws()["assets"] if a["id"] == asset["id"])["facts"]
        self.assertEqual([f["category"] for f in facts], ["卖什么", "购买路径"])
        self.assertFalse(any(f["demo"] for f in facts))

    def test_fabricated_quote_rejected(self):
        content = "山野咖啡冷萃挂耳，12 克一包。"
        good = {"facts": [{"category": "卖什么", "fact": "冷萃挂耳", "quote": "12 克一包"}]}
        adapters.validate_facts(good, content)
        with self.assertRaises(ValueError):
            adapters.validate_facts({"facts": [{"category": "卖什么", "fact": "编造要点", "quote": "原文里没有的句子"}]}, content)
        with self.assertRaises(ValueError):
            adapters.validate_facts({"facts": [{"category": "随想", "fact": "冷萃挂耳", "quote": "12 克一包"}]}, content)
        with self.assertRaises(ValueError):
            adapters.validate_facts({"facts": []}, content)

    def test_kind_gates_and_isolation(self):
        # 图片与禁用词不整理
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2uoAAAAASUVORK5CYII="
        status, image = self.post("/api/assets", {"name": "产品图", "kind": "图片", "content": photo})
        self.assertEqual(status, 200)
        status, banned = self.post("/api/assets", {"name": "禁用词", "kind": "禁用词", "content": "最好,第一"})
        self.assertEqual(status, 200)
        self.assertIsNone(self.latest_facts_task())
        self.assertEqual(self.post(f"/api/assets/{image['id']}/facts", {})[0], 400)
        self.assertEqual(self.post(f"/api/assets/{banned['id']}/facts", {})[0], 400)
        # 越权：其他项目看不到这份资料
        other = Client(self.c.base)
        other.req("/api/auth/demo", "POST", {})
        op = other.req("/api/bootstrap")[1]["projects"][0]["id"]
        self.assertEqual(
            other.req(f"/api/assets/{image['id']}/facts", "POST", {"project_id": op})[0], 404
        )

    def test_delete_asset_removes_facts(self):
        status, asset = self.post("/api/assets", {"name": "产品", "kind": "产品信息", "content": PRODUCT})
        jobs.run(self.latest_facts_task())
        self.c.req(f"/api/assets/{asset['id']}", "DELETE", {"project_id": self.p})
        with D.db() as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM asset_facts WHERE asset_id=?", (asset["id"],)).fetchone()[0], 0
            )

    def formal_account(self):
        user = app.new_user("formal@facts.test", "test-password-123")
        self.c.req("/api/auth/login", "POST", {"email": "formal@facts.test", "password": "test-password-123"})
        self.p = self.c.req("/api/bootstrap")[1]["projects"][0]["id"]
        from server import access
        admin = app.new_user("admin@facts.test", "test-admin-password", "admin")
        with D.db() as c:
            c.execute("BEGIN IMMEDIATE")
            access.approve(c, user, admin, "test_admin", preserve_balance=True)
        return user

    def test_original_prompt_carries_structured_facts(self):
        self.formal_account()
        status, asset = self.post("/api/assets", {"name": "产品", "kind": "产品信息", "content": PRODUCT})
        with D.db() as c:
            c.execute(
                "INSERT INTO asset_facts VALUES (?,?,?,?,?,?,?,?)",
                (D.uid(), asset["id"], self.p, "卖什么", "冷萃挂耳 12 克一包", "12 克一包", 0, D.now()),
            )
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        seen = []

        def fake(prompt, schema, version, kind="analyze", validator=None):
            seen.append(json.loads(json.dumps(prompt)))
            outputs = adapters.demo_outputs("xhs", "t", prompt.get("batch", 1))
            result = {"outputs": outputs}
            if validator:
                validator(result)
            return result, "fake/model"

        with patch.object(adapters, "model_json", side_effect=fake):
            status, r = self.post("/api/original", {"platform": "xhs", "topic": "冷萃挂耳", "assets": [asset["id"]]})
            self.assertEqual(status, 202, r)
            jobs.run(r["task_ids"][0])
        prompt = seen[-1]
        self.assertEqual(prompt["structured_facts"][0]["fact"], "冷萃挂耳 12 克一包")
        self.assertEqual(prompt["structured_facts"][0]["quote"], "12 克一包")


if __name__ == "__main__":
    unittest.main()
