"""内容生产线（PRD 9.5）：工序、发布账号、第一小时清单与导出；不回填数据。"""

import importlib, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

D = importlib.import_module("server.db")
from server import app, jobs, production
from tests.test_app import Client


class TrackingApiTests(unittest.TestCase):
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
        r = self.post("/api/original", {"platform": "xhs", "topic": "冷萃挂耳", "temporary": "12 克一包"})[1]
        jobs.run(r["task_ids"][0])
        self.ids = [c["id"] for c in self.ws()["creations"]]

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

    def test_flow_publish_checklist_export(self):
        cid = self.ids[0]
        self.assertEqual(self.ws()["creations"][0]["tracking"], {"status": "draft", "checklist": {}})
        acc = self.post("/api/assets", {"name": "山野咖啡主号", "kind": "账号", "content": "通勤人群"})[1]["id"]
        other = self.post("/api/assets", {"name": "产品", "kind": "产品信息", "content": "x"})[1]["id"]
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"status": "published", "account_id": other})[0], 400)
        status, t = self.post(f"/api/tracking/{cid}", {"status": "published", "account_id": acc})
        self.assertEqual(status, 200, t)
        self.assertEqual(t["status"], "published")
        self.assertTrue(t["published_at"])
        status, t = self.post(f"/api/tracking/{cid}", {"checklist": {"pinned": True, "knowledge": 1, "hack": True}})
        self.assertEqual(t["checklist"], {"pinned": True, "knowledge": True, "atmosphere": False})
        # 状态与账号在后续更新中保留；不存在数据回填
        self.assertEqual(t["account_id"], acc)
        self.assertNotIn("metrics", t)
        self.assertNotIn("evaluation", t)
        status, t = self.post(f"/api/tracking/{cid}", {"metrics": {"impressions": 2000}})
        self.assertNotIn("metrics", t)
        status, csv = self.c.req(f"/api/export?project_id={self.p}", raw=True)
        text = csv.decode()
        for col in ("工序状态", "发布账号", "发布时间", "山野咖啡主号", "已发布", "待发布"):
            self.assertIn(col, text)
        for gone in ("曝光", "点击率", "投放建议"):
            self.assertNotIn(gone, text.splitlines()[0])
        t = self.post(f"/api/tracking/{cid}", {"status": "draft"})[1]
        self.assertIsNone(t["published_at"])
        self.assertEqual(t["checklist"], {})

    def test_isolation_and_validation(self):
        cid = self.ids[0]
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"status": "sent"})[0], 400)
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"status": "published", "published_at": "昨天"})[0], 400)
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"checklist": "yes"})[0], 400)
        self.assertEqual(self.post("/api/tracking/abcdef", {"status": "published"})[0], 404)
        other = Client(self.c.base)
        other.req("/api/auth/demo", "POST", {})
        op = other.req("/api/bootstrap")[1]["projects"][0]["id"]
        self.assertIn(other.req(f"/api/tracking/{cid}", "POST", {"project_id": self.p, "status": "published"})[0], (403, 404))
        self.assertEqual(other.req(f"/api/tracking/{cid}", "POST", {"project_id": op, "status": "published"})[0], 404)
        self.c.req(f"/api/creations/{cid}", "DELETE", {"project_id": self.p})
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"status": "published"})[0], 404)

    def test_old_table_with_metrics_column_still_works(self):
        with D.db() as c:
            c.execute("DROP TABLE creation_tracking")
            c.execute(
                "CREATE TABLE creation_tracking(creation_id TEXT PRIMARY KEY,project_id TEXT,status TEXT NOT NULL DEFAULT 'draft',account_id TEXT,published_at TEXT,metrics TEXT,checklist TEXT,updated_at TEXT)"
            )
        status, t = self.post(f"/api/tracking/{self.ids[0]}", {"status": "published"})
        self.assertEqual(status, 200, t)
        self.assertEqual(self.ws()["creations"][0]["tracking"]["status"] in ("draft", "published"), True)


if __name__ == "__main__":
    unittest.main()
