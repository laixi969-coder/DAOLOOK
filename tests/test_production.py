"""内容生产线（PRD 9.5）：工序、发布账号、第一小时清单与导出；不回填数据。"""

import csv, importlib, io, tempfile, threading, unittest, zipfile
from xml.etree import ElementTree
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
        r = self.post("/api/original", {"platform": "xhs", "topic": "冷萃挂耳", "temporary": "12 克一包", "skip_question": True})[1]
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

    def test_board_stats_full_project_scope(self):
        creations = self.ws()["creations"]
        stats = self.ws()["stats"]
        self.assertEqual(stats["total"], len(creations))
        self.assertEqual(stats["today"], len(creations))  # 均为刚刚生成
        self.assertEqual(stats["published"], 0)
        self.assertEqual(stats["results"], {"recorded": 0, "views": 0, "leads": 0, "orders": 0})
        # 演示批量同时包含两种内容方向
        self.assertEqual(sum(stats["directions"]["xhs"].values()), len(creations))
        self.assertGreaterEqual(len(stats["directions"]["xhs"]), 2)
        cid = self.ids[0]
        self.post(f"/api/tracking/{cid}", {"status": "published"})
        self.post(f"/api/results/{cid}", {"results": {"views": 120, "leads": 3}})
        stats = self.ws()["stats"]
        self.assertEqual(stats["published"], 1)
        # 演示稿不计入效果合计，与看板既有口径一致
        self.assertEqual(stats["results"], {"recorded": 0, "views": 0, "leads": 0, "orders": 0})

    def formal(self, ids, goal="leads"):
        with D.db() as c:
            c.executemany("UPDATE creation_outputs SET data=json_set(data,'$.demo',0,'$.goal',?) WHERE id=?",
                          [(goal, cid) for cid in ids])

    def test_confirmation_tracks_the_reviewed_revision_and_first_batch_latency(self):
        cid, second, other = self.ids[:3]
        self.formal([cid, second, other])
        base = "2026-01-01T12:00:00+00:00"
        with D.db() as c:
            c.execute("UPDATE tasks SET created_at=? WHERE id=(SELECT task_id FROM creation_outputs WHERE id=?)",(base,cid))
        ready = f"/api/creations/{cid}/ready"
        with patch("server.editing.now",return_value="2026-01-01T12:02:00+00:00"):
            status, confirmed = self.post(ready, {"revision":0})
        self.assertEqual(status,200,confirmed)
        self.assertEqual(self.post(ready, {"revision":0})[1],confirmed)
        self.assertEqual(self.post(ready, {"revision":1})[0],409)
        other_project = self.c.req("/api/projects", "POST", {"name":"另一个项目"})[1]["id"]
        self.assertEqual(self.post(ready, {"revision":0, "project_id":other_project})[0],404)
        self.assertEqual(self.post(f"/api/creations/{cid}/edit", {"revision":0,"changes":{"title":"核对后的标题"}})[0],200)
        row = next(row for row in self.ws()["creations"] if row["id"]==cid)
        self.assertIsNone(row["ready_at"])
        self.assertEqual(self.post(ready,{"revision":0})[0],409)
        self.assertEqual(self.post(ready,{"revision":1})[0],200)
        self.post(f"/api/creations/{second}/ready",{"revision":0})
        self.post(f"/api/tracking/{other}",{"status":"published"})
        self.assertEqual(self.post(f"/api/creations/{other}/ready",{"revision":0})[0],409)
        self.assertEqual(self.ws()["stats"]["delivery"], {
            "formal":3,"published":1,"confirmed_batches":1,"first_ready_seconds":120,
        })

    def test_fixed_windows_roundtrip_weighted_comparisons_and_exports(self):
        first, second, demo, draft = self.ids[:4]
        self.formal([first,second,draft])
        dates = {"status":"published","published_at":"2026-01-01T12:00:00+00:00"}
        account = self.post("/api/assets",{"kind":"账号","name":"门店账号","content":"门店内容"})[1]["id"]
        for cid in (first,second,demo):
            self.post(f"/api/tracking/{cid}",{**dates,"account_id":account})
        path = f"/api/results/{first}"
        def save(cid,period,metrics):
            status,res = self.post(f"/api/results/{cid}",{"window":period,"results":metrics})
            self.assertEqual(status,200,res)
        save(first,"lifetime",{"views":500,"note":"顾客问了场次"})
        old = next(c["results"]["recorded_at"] for c in self.ws()["creations"] if c["id"]==first)
        save(first,"24h",{"views":100,"leads":2})
        save(first,"24h",{"views":120,"leads":0})
        save(first,"7d",{"views":250,"leads":4})
        save(first,"lifetime",{"views":550,"note":"顾客问了场次"})
        save(second,"24h",{"leads":3})
        save(demo,"24h",{"views":5000,"leads":200})
        save(draft,"lifetime",{"views":1000})
        ws = self.ws()
        snapshot = next(c["results"] for c in ws["creations"] if c["id"]==first)
        self.assertEqual(snapshot["windows"]["24h"]["leads"],0)
        self.assertNotIn("orders",snapshot["windows"]["24h"])
        self.assertEqual(snapshot["note"],"顾客问了场次")
        stats = ws["stats"]
        self.assertEqual(stats["results"],{"recorded":2,"views":550,"leads":0,"orders":0})
        self.assertEqual(stats["metric_counts"],{"views":1,"leads":0,"orders":0})
        self.assertEqual(stats["account_published"][account],3)
        groups = {row["window"]:row for row in stats["goal_windows"]}
        self.assertEqual(groups["24h"],{"platform":"xhs","goal":"leads","window":"24h","posts":2,
                         "total":3,"paired_posts":1,"paired_views":120,"paired_actions":0})
        self.assertEqual(groups["7d"]["paired_actions"],4)
        history = jobs.history_results(self.p,"xhs","leads")
        self.assertTrue(any(entry["results"].get("windows",{}).get("7d",{}).get("views")==250 for entry in history))
        self.assertEqual(self.post(path,{"expected_updated_at":old,"results":{}})[0],409)
        self.assertEqual(self.post(path,{"expected_published_at":"earlier post","window":"24h","results":{}})[0],409)
        url = f"/api/export?project_id={self.p}"
        rows = csv.DictReader(io.StringIO(self.c.req(url,raw=True)[1].decode("utf-8-sig")))
        row = next(r for r in rows if r["稿件ID"]==first)
        self.assertEqual([row[k] for k in ("浏览次数","24小时有效咨询","24小时订单数","7天浏览次数")],["550","0","","250"])
        with zipfile.ZipFile(io.BytesIO(self.c.req(url+"&format=xlsx",raw=True)[1])) as file:
            xml = ElementTree.fromstring(file.read("xl/worksheets/sheet1.xml"))
        vals = [[cell.text or "" for cell in r.findall(".//{*}t")] for r in xml.findall(".//{*}row")]
        excel = next(dict(zip(vals[0],v)) for v in vals[1:] if v[0]==first)
        self.assertEqual(excel["24小时有效咨询"],"0")
        self.assertEqual(excel["24小时订单数"],"")
        save(first,"7d",{})
        self.assertNotIn("7d",[r["window"] for r in self.ws()["stats"]["goal_windows"]])
        self.post(f"/api/tracking/{first}",{"status":"draft"})
        self.assertEqual(self.post(path,{"window":"24h","results":{"leads":0}})[0],400)
        self.post(f"/api/tracking/{first}",{"status":"published"})
        self.assertEqual(self.post(path,{"window":"24h","results":{"leads":0}})[0],400)
        self.assertEqual(self.post(path,{"window":"2d","results":{}})[0],400)
        current = next(c for c in self.ws()["creations"] if c["id"]==first)
        self.assertEqual(current["results"]["windows"],{})

    def test_goal_metrics_are_separate_and_require_the_actual_objective(self):
        groups = {}
        for platform, goal, numbers in [("tiktok","reach",{"views":0}),("instagram","sales",{"orders":5}),
                                        ("instagram","sales",{"views":100,"orders":2}),("instagram","leads",{"orders":10})]:
            production.add_goal_window(groups,platform,goal,"7d",numbers)
        self.assertEqual(len(groups),2)
        self.assertEqual(groups["tiktok","reach","7d"]["posts"],1)
        self.assertEqual(groups["instagram","sales","7d"]["total"],7)
        self.assertEqual(groups["instagram","sales","7d"]["paired_actions"],2)

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
