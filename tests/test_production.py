"""内容生产线（PRD 9.5）：工序、第一小时清单、数据回填、投放判断、账号矩阵、导出。"""

import importlib, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

D = importlib.import_module("server.db")
from server import app, jobs, production
from tests.test_app import Client

LIMITS = {"promote_ctr": 0.2, "promote_min_impressions": 500}


class EvaluateTests(unittest.TestCase):
    def test_advice(self):
        self.assertIsNone(production.evaluate({}, LIMITS))
        self.assertEqual(production.evaluate({"likes": 3}, LIMITS)["advice"], "unknown")
        self.assertEqual(
            production.evaluate({"impressions": 300, "clicks": 200}, LIMITS)["advice"],
            "insufficient",
        )
        good = production.evaluate(
            {"impressions": 1000, "clicks": 250, "likes": 20, "saves": 5}, LIMITS
        )
        self.assertEqual(good["advice"], "promote")
        self.assertEqual(good["ctr"], 0.25)
        self.assertEqual(good["engagement"], 0.1)
        self.assertIn("小额保护性投放", good["advice_text"])
        low = production.evaluate({"impressions": 1000, "clicks": 150}, LIMITS)
        self.assertEqual(low["advice"], "hold")
        self.assertIn("不建议投放", low["advice_text"])
        self.assertEqual(
            production.evaluate({"impressions": 1000, "clicks": 150}, {"promote_ctr": 0.1})["advice"],
            "promote",
        )

    def test_clean_metrics(self):
        self.assertEqual(production.clean_metrics({"impressions": 10, "clicks": ""}), {"impressions": 10})
        for bad in ({"impressions": -1}, {"clicks": 1.5}, {"likes": "3"}, {"likes": True}, {"impressions": 5, "clicks": 6}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                production.clean_metrics(bad)


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

    def test_flow_publish_checklist_metrics_export(self):
        cid = self.ids[0]
        self.assertEqual(self.ws()["creations"][0]["tracking"]["status"], "draft")
        acc = self.post("/api/assets", {"name": "山野咖啡主号", "kind": "账号", "content": "通勤人群"})[1]["id"]
        other = self.post("/api/assets", {"name": "产品", "kind": "产品信息", "content": "x"})[1]["id"]
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"status": "published", "account_id": other})[0], 400)
        status, t = self.post(f"/api/tracking/{cid}", {"status": "published", "account_id": acc})
        self.assertEqual(status, 200, t)
        self.assertEqual(t["status"], "published")
        self.assertTrue(t["published_at"])
        status, t = self.post(f"/api/tracking/{cid}", {"checklist": {"pinned": True, "knowledge": 1, "hack": True}})
        self.assertEqual(t["checklist"], {"pinned": True, "knowledge": True, "atmosphere": False})
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"metrics": {"impressions": 10, "clicks": 20}})[0], 400)
        status, t = self.post(f"/api/tracking/{cid}", {"metrics": {"impressions": 2000, "clicks": 500, "likes": 40}})
        self.assertEqual(t["evaluation"]["advice"], "promote")
        # 状态与账号在后续更新中保留
        self.assertEqual(t["status"], "published")
        self.assertEqual(t["account_id"], acc)
        tr = next(c for c in self.ws()["creations"] if c["id"] == cid)["tracking"]
        self.assertEqual(tr["evaluation"]["ctr"], 0.25)
        status, csv = self.c.req(f"/api/export?project_id={self.p}", raw=True)
        text = csv.decode()
        for col in ("工序状态", "发布账号", "点击率", "投放建议", "山野咖啡主号", "25.0%", "小额保护性投放", "待发布"):
            self.assertIn(col, text)
        # 撤回为待发布：清空发布时间与清单，保留数据
        t = self.post(f"/api/tracking/{cid}", {"status": "draft"})[1]
        self.assertIsNone(t["published_at"])
        self.assertEqual(t["checklist"], {})
        self.assertEqual(t["metrics"]["impressions"], 2000)

    def test_isolation_and_validation(self):
        cid = self.ids[0]
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"status": "sent"})[0], 400)
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"status": "published", "published_at": "昨天"})[0], 400)
        self.assertEqual(self.post("/api/tracking/abcdef", {"status": "published"})[0], 404)
        other = Client(self.c.base)
        other.req("/api/auth/demo", "POST", {})
        op = other.req("/api/bootstrap")[1]["projects"][0]["id"]
        self.assertIn(other.req(f"/api/tracking/{cid}", "POST", {"project_id": self.p, "status": "published"})[0], (403, 404))
        self.assertEqual(other.req(f"/api/tracking/{cid}", "POST", {"project_id": op, "status": "published"})[0], 404)
        self.c.req(f"/api/creations/{cid}", "DELETE", {"project_id": self.p})
        self.assertEqual(self.post(f"/api/tracking/{cid}", {"status": "published"})[0], 404)

    def test_default_promote_thresholds(self):
        limits = D.setting("limits")
        self.assertEqual(limits["promote_ctr"], 0.2)
        self.assertEqual(limits["promote_min_impressions"], 500)


if __name__ == "__main__":
    unittest.main()
