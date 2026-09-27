"""自主创作（PRD 9.4）：依据校验、赛道参考、再来一批、计费、导出与 Skill 发布。"""

import importlib, json, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

D = importlib.import_module("server.db")
from server import app, jobs, adapters
from tests.test_app import Client


class OriginalTests(unittest.TestCase):
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
        self.assertEqual(self.c.req("/api/auth/demo", "POST", {})[0], 200)
        self.p = self.c.req("/api/bootstrap")[1]["projects"][0]["id"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.queue.stop()
        D.DB_PATH = self.original
        self.temp.cleanup()

    def post(self, path, data):
        return self.c.req(path, "POST", {"project_id": self.p, **data})

    def run_task(self, r):
        for ident in r["task_ids"]:
            jobs.run(ident)
        with D.db() as c:
            return [
                dict(c.execute("SELECT * FROM tasks WHERE id=?", (i,)).fetchone())
                for i in r["task_ids"]
            ]

    def ws(self):
        return self.c.req(f"/api/workspace?project_id={self.p}")[1]

    def asset(self):
        status, r = self.post(
            "/api/assets",
            {"name": "产品", "kind": "产品信息", "content": "山野咖啡冷萃挂耳，12 克一包，售价 XX"},
        )
        self.assertEqual(status, 200)
        return r["id"]

    def test_requires_basis_and_valid_input(self):
        base = {"platform": "xhs", "topic": "冷萃挂耳"}
        status, body = self.post("/api/original", base)
        self.assertEqual(status, 400)
        self.assertIn("依据", body["error"])
        self.assertEqual(self.post("/api/original", {**base, "platform": "weibo", "temporary": "x"})[0], 400)
        self.assertEqual(self.post("/api/original", {**base, "topic": "x", "temporary": "x"})[0], 400)
        self.assertEqual(self.post("/api/original", {**base, "assets": ["nope"]})[0], 400)
        self.assertEqual(self.post("/api/original", {"brief_id": "missing", "temporary": "x"})[0], 404)

    def test_demo_flow_batch_again_and_export(self):
        aid = self.asset()
        before = self.c.req("/api/bootstrap")[1]["credits"]["balance"]
        status, r = self.post(
            "/api/original", {"platform": "xhs", "topic": "冷萃挂耳", "assets": [aid]}
        )
        self.assertEqual(status, 202)
        task = self.run_task(r)[0]
        self.assertEqual(task["state"], "SUCCEEDED", task)
        self.assertEqual(task["cost"], 15)
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], before - 15)
        ws = self.ws()
        self.assertEqual(len(ws["briefs"]), 1)
        brief = ws["briefs"][0]
        self.assertEqual(brief["id"], r["brief_id"])
        self.assertNotIn(brief["id"], [s["id"] for s in ws["sources"]])
        self.assertEqual(brief["data"]["assets"], [aid])
        self.assertTrue(brief["data"]["benchmark"]["examples"])
        outs = [c for c in ws["creations"] if c["source_id"] == brief["id"]]
        self.assertEqual(len(outs), 8)
        self.assertTrue(all(o["data"]["origin"] == "original" for o in outs))
        adapters.validate_creation({"outputs": [o["data"] for o in outs]}, "xhs")
        # 再来一批：沿用资料，追加，不覆盖
        status, r2 = self.post("/api/original", {"brief_id": brief["id"]})
        self.assertEqual(status, 202)
        self.assertEqual(r2["brief_id"], brief["id"])
        self.assertEqual(self.run_task(r2)[0]["state"], "SUCCEEDED")
        ws = self.ws()
        self.assertEqual(len(ws["briefs"]), 1)
        self.assertEqual(len([c for c in ws["creations"] if c["source_id"] == brief["id"]]), 16)
        status, csv = self.c.req(f"/api/export?project_id={self.p}", raw=True)
        self.assertIn("自主创作：冷萃挂耳", csv.decode())
        # 封面可以基于自主创作稿件规划
        status, plan = self.post("/api/cover/plan", {"creation_id": outs[0]["id"]})
        self.assertEqual(status, 200, plan)

    def test_live_passes_benchmark_note_previous_and_assets(self):
        aid = self.asset()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        seen = []

        def fake(prompt, schema, version, kind, validator):
            seen.append(json.loads(json.dumps(prompt)))
            outputs = adapters.demo_outputs("douyin", "t", 1)
            validator({"outputs": outputs})
            return {"outputs": outputs}, "fake/model"

        with patch.object(adapters, "model_json", side_effect=fake):
            r = self.post(
                "/api/original",
                {"platform": "douyin", "topic": "冷萃挂耳", "keyword": "挂耳咖啡", "assets": [aid]},
            )[1]
            self.assertEqual(self.run_task(r)[0]["state"], "SUCCEEDED")
            r2 = self.post("/api/original", {"brief_id": r["brief_id"]})[1]
            self.assertEqual(self.run_task(r2)[0]["state"], "SUCCEEDED")
        first, second = seen
        self.assertEqual(first["brief"], {"platform": "douyin", "topic": "冷萃挂耳"})
        self.assertIn("未取得赛道参考", first["benchmark"]["note"])
        self.assertEqual(first["benchmark"]["keyword"], "挂耳咖啡")
        self.assertIn("山野咖啡", first["assets"][0]["content"])
        self.assertEqual(first["previous_outputs"], [])
        self.assertEqual(len(second["previous_outputs"]), 8)
        self.assertEqual(second["batch"], 2)
        self.assertNotIn("reference", first)
        self.assertIn("不得改写、照搬", first["instruction"])
        with D.db() as c:
            skill = c.execute(
                "SELECT skill_version FROM tasks WHERE id=?", (r["task_ids"][0],)
            ).fetchone()[0]
            name = c.execute("SELECT name FROM skill_versions WHERE id=?", (skill,)).fetchone()[0]
        self.assertEqual(name, "douyin_original")

    def test_live_benchmark_uses_search_results(self):
        raw = {
            "data": [
                {"note_id": f"n{i}", "title": f"样本{i}", "interact_info": {"liked_count": v}}
                for i, v in enumerate([10, 500, 30, 80, 2, 60])
            ]
        }
        with patch.object(adapters.TikHubAdapter, "searchContents", return_value=raw):
            bench = adapters.fetch_benchmark("挂耳", "xhs")
        self.assertEqual(bench["pool"], 6)
        self.assertEqual(len(bench["examples"]), 5)
        self.assertEqual(bench["examples"][0]["title"], "样本1")
        self.assertEqual(bench["note"], "")

    def test_failure_refunds_and_leaves_no_brief(self):
        aid = self.asset()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        before = self.c.req("/api/bootstrap")[1]["credits"]["balance"]
        r = self.post("/api/original", {"platform": "xhs", "topic": "冷萃挂耳", "assets": [aid]})[1]
        with patch.object(adapters, "model_json", side_effect=ValueError("模型失败")):
            try:
                jobs.run(r["task_ids"][0])
            except ValueError as e:
                jobs.fail(r["task_ids"][0], str(e))
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], before)
        self.assertEqual(self.ws()["briefs"], [])

    def test_original_skills_published_and_rule_fallback(self):
        with D.db() as c:
            names = {
                r[0]
                for r in c.execute("SELECT name FROM skill_versions WHERE status='Published'")
            }
        self.assertTrue({"xhs_original", "douyin_original"} <= names)
        self.assertEqual(jobs.task_cost("original", {}, {"analyze": 5, "create": 12, "cover": 8}), (12, 12))
        self.assertEqual(jobs.task_cost("original", {}, {"analyze": 5, "create": 12, "cover": 8, "original": 20}), (20, 20))


if __name__ == "__main__":
    unittest.main()
