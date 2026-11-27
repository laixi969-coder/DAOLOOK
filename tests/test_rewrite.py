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

    def make_draft(self, platform="xhs", **fields):
        status, r = self.post(
            "/api/original",
            {"platform": platform, "topic": "冷萃挂耳", "temporary": "冷萃挂耳每包12克，私信咨询", "skip_question": True, **fields},
        )
        self.assertEqual(status, 202, r)
        jobs.run(r["task_ids"][0])
        return next(item["id"] for item in self.ws()["creations"] if item["task_id"] == r["task_ids"][0])

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
        # Publishing a queued draft also prevents spending a model call.
        before = self.credits()
        status, pending = self.post(f"/api/creations/{cid}/rewrite", {"revision": 0, "instruction": "改成送礼场景"})
        self.assertEqual(status, 202, pending)
        task = pending["task_ids"][0]
        self.post(f"/api/tracking/{cid}", {"status": "published"})
        with patch.object(adapters, "rewrite", side_effect=AssertionError("已发布稿件不应继续重写")):
            with self.assertRaisesRegex(ValueError, "已发布") as error:
                jobs.run(task)
        jobs.fail(task, str(error.exception))
        self.assertEqual(self.credits(), before)
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
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2uoAAAAASUVORK5CYII="
        image_id = self.post("/api/assets", {"kind":"图片", "name":"产品照片", "content":photo})[1]["id"]
        cid = self.make_draft(goal="sales", assets=[image_id], temporary="冷萃挂耳售价199元，仅限到店。")
        with D.db() as c:
            original = json.loads(c.execute("SELECT data FROM creation_outputs WHERE id=?", (cid,)).fetchone()[0])
            original.update(demo=False, evidence=[{"asset_id":"temporary", "quote":"冷萃挂耳售价199元"}])
            c.execute("UPDATE creation_outputs SET data=? WHERE id=?", (D.dumps(original), cid))
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        seen = []

        def provider_response(url, key, payload, timeout, billing=None):
            self.assertEqual(billing, "model:test/model")
            seen.append(json.loads(payload["messages"][1]["content"]))
            result = {"output": {"body": "加班时想喝冷萃？现在只要99元。" + original["cta"],
                                "comments": {"pinned":"欢迎留言咨询。"},
                                "goal":"reach", "demo":True, "batch":999, "evidence":[],
                                "image_asset_ids":[],
                                "topic_basis":{}, "quality":{"status":"checked","issues":[]}}}
            return {"choices":[{"message":{"content":json.dumps(result)}}]}

        route = [("test", {"base_url":"https://example.invalid", "api_key":"test"}, "model")]
        with patch.object(adapters, "candidates", return_value=route) as routes, patch.object(adapters, "request_json", side_effect=provider_response):
            status, r = self.post(f"/api/creations/{cid}/rewrite", {"revision": 0, "instruction": "开头换成加班场景"})
            self.assertEqual(status, 202, r)
            jobs.run(r["task_ids"][0])
        routes.assert_called_once_with("create")
        self.assertEqual(seen[0]["instruction"], "开头换成加班场景")
        self.assertTrue(seen[0]["draft"]["title"])
        self.assertEqual(seen[0]["context"]["goal"], "sales")
        self.assertEqual([a["id"] for a in seen[0]["assets"]], ["temporary"])
        creation = next(x for x in self.ws()["creations"] if x["id"] == cid)
        data = creation["data"]
        self.assertIn("99元", data["body"])
        for key in ("goal", "demo", "batch", "image_asset_ids", "image_suggestions", "evidence", "origin", "direction", "role", "angle"):
            self.assertEqual(data[key], original[key], key)
        self.assertEqual(data["image_asset_ids"], [image_id])
        self.assertEqual(data["comment_layout"]["pinned"]["text"], "欢迎留言咨询。")
        self.assertEqual(data["comment_layout"]["pinned"]["goal"], original["comment_layout"]["pinned"]["goal"])
        self.assertEqual(data["topic_basis"]["sources"], original["topic_basis"]["sources"])
        self.assertTrue(data["topic_basis"]["review_required"])
        self.assertEqual(data["quality"]["status"], "needs_input")
        self.assertTrue(any(c["kind"] == "price" and c["value"] == "99元" and c["status"] == "review"
                            for c in data["quality"]["claim_checks"]), data["quality"])
        self.assertEqual(creation["revision"], 1)

    def test_rewrite_keeps_context_for_both_platforms_and_all_goals(self):
        for platform in ("xhs", "douyin"):
            for goal in ("reach", "leads", "sales"):
                with self.subTest(platform=platform, goal=goal):
                    draft = {**adapters.demo_outputs(platform, "冷萃", 1)[0], "goal":goal, "image_asset_ids":["photo"]}
                    with patch.object(adapters, "model_json", return_value=({"output":{"title":"加班喝哪款？"}}, "test")):
                        edited, _ = adapters.rewrite(draft, "换标题", "", platform)
                    self.assertEqual((edited["goal"], edited["image_asset_ids"], edited["title"]), (goal, ["photo"], "加班喝哪款？"))
                    self.assertEqual(edited["demo"], draft["demo"])
                    self.assertEqual(edited["storyboard"], draft["storyboard"])
        for invalid in ({}, {"quality":{}}, {"title":" "}, {"tags":[123]}, {"body":draft["body"]}):
            with self.subTest(invalid=invalid), patch.object(adapters, "model_json", return_value=({"output":invalid}, "test")):
                with self.assertRaises(ValueError):
                    adapters.rewrite(draft, "换标题", "", "douyin")

    def test_storyboard_only_edit_checks_spoken_price_and_preserves_metadata(self):
        draft = {**adapters.demo_outputs("douyin", "冷萃", 1)[0], "demo":False, "goal":"sales",
                 "image_asset_ids":["photo"], "campaign_metadata":{"owner":"项目甲"}, "script":"原口播"}
        assets = [{"id":"price", "content":"冷萃售价199元。", "kind":"产品信息"}]
        shots = ["0–3秒，字幕：冷萃售价99元。", "3–6秒，打开冷萃包装。"]
        reply = {"storyboard":shots, "goal":"reach", "image_asset_ids":[], "campaign_metadata":{"owner":"未知"}}
        with patch.object(adapters, "model_json", return_value=({"output":reply}, "test")):
            edited, _ = adapters.rewrite(draft, "只改分镜", "", "douyin", assets=assets)
        self.assertEqual(edited["storyboard"], shots)
        for key in ("body","script","goal","image_asset_ids","campaign_metadata","image_suggestions","shooting_list"):
            self.assertEqual(edited[key], draft[key], key)
        self.assertTrue(any(item["kind"]=="price" and item["status"]=="review" and "99元" in item["sentence"]
                            for item in edited["quality"]["claim_checks"]))
        for key in ("shooting_list","image_suggestions","script"):
            value = "只改口播" if key == "script" else ["只拍产品包装"]
            with self.subTest(key=key), patch.object(adapters, "model_json", return_value=({"output":{key:value}}, "test")):
                updated, _ = adapters.rewrite(draft, "调整这一项", "", "douyin", assets=assets)
                self.assertEqual(updated[key], value)
                self.assertEqual(updated["image_asset_ids"], draft["image_asset_ids"])

    def test_alternate_titles_and_legacy_comment_copy(self):
        draft = {**adapters.demo_outputs("xhs", "冷萃", 1)[0], "demo":False}
        titles = ["冷萃99元？", "冷萃怎么喝", "办公室冲泡"]
        reply = {"titles":titles, "comment_layout":{"pinned":{"text":"你喜欢什么风味？", "goal":"改写置顶目标"},
                 "atmosphere":["你试过吗？"], "first_hour":"改写运营安排"}}
        with patch.object(adapters, "model_json", return_value=({"output":reply}, "test")):
            edited, _ = adapters.rewrite(draft, "换标题备选和置顶评论", "", "xhs")
        self.assertEqual(edited["titles"], titles)
        self.assertEqual(edited["title"], draft["title"])
        self.assertEqual(edited["comment_layout"]["pinned"]["text"], "你喜欢什么风味？")
        self.assertEqual(edited["comment_layout"]["pinned"]["goal"], draft["comment_layout"]["pinned"]["goal"])
        self.assertEqual(edited["comment_layout"]["first_hour"], draft["comment_layout"]["first_hour"])
        self.assertEqual(edited["comment_layout"]["knowledge"], draft["comment_layout"]["knowledge"])
        self.assertEqual(edited["comment_layout"]["atmosphere"], ["你试过吗？"])
        self.assertTrue(any(check["value"]=="99元" for check in edited["quality"]["claim_checks"]))
        for invalid in ({"titles":["一个标题"]}, {"shooting_list":["x"*2001]}, {"storyboard":[{}]},
                        {"comment_layout":{"knowledge":"错误格式"}}):
            with self.subTest(invalid=invalid), patch.object(adapters, "model_json", return_value=({"output":invalid}, "test")):
                with self.assertRaises(ValueError):
                    adapters.rewrite(draft, "按要求修改", "", "xhs")

    def test_rewrite_checks_public_copy_in_artwork_and_keeps_required_copy(self):
        for platform,key in (("xhs","image_suggestions"), ("douyin","shooting_list")):
            draft = adapters.demo_outputs(platform, "冷萃", 1)[0]
            reply = {key:["画面价签写上99元", "准备500ml量杯"]}
            with patch.object(adapters, "model_json", return_value=({"output":reply}, "test")):
                updated, _ = adapters.rewrite(draft, "改产品的价签", "", platform, assets=[{"id":"p","content":"售价199元"}])
            checks = updated["quality"]["claim_checks"]
            self.assertTrue(any(c["kind"] == "price" and "99元" in c["value"] and c["status"] == "review" for c in checks))
            self.assertFalse(any("量杯" in c["sentence"] for c in checks))
            destructive = {"comments":{"pinned":" "}} if platform == "xhs" else {"hook":" "}
            for missing in (destructive, {"cover_text":""}):
                with patch.object(adapters, "model_json", return_value=({"output":{"title":"换个标题",**missing}}, "test")):
                    with self.assertRaises(ValueError):
                        adapters.rewrite(draft, "换标题", "", platform)

    def test_next_rewrite_recovers_missing_context_from_initial_version_or_generation_task(self):
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2uoAAAAASUVORK5CYII="
        image_id = self.post("/api/assets", {"kind":"图片", "name":"展示图片", "content":photo})[1]["id"]
        cid = self.make_draft(goal="reach", assets=[image_id])
        with D.db() as c:
            row = c.execute("SELECT data,created_at FROM creation_outputs WHERE id=?", (cid,)).fetchone()
            first = json.loads(row["data"])
            # Old version 0 retains the image IDs; the original generation task retains the goal.
            del first["goal"]
            c.execute("INSERT INTO creation_revisions VALUES (?,?,?,?,?)", (cid,0,D.dumps(first),"初始稿",row["created_at"]))
            legacy = {k:v for k,v in first.items() if k != "image_asset_ids"}
            c.execute("INSERT INTO creation_revisions VALUES (?,?,?,?,?)", (cid,1,D.dumps(legacy),"AI 定向重写",D.now()))
            c.execute("UPDATE creation_outputs SET data=? WHERE id=?", (D.dumps(legacy),cid))
        status, r = self.post(f"/api/creations/{cid}/rewrite", {"revision":1, "instruction":"精简一下正文"})
        self.assertEqual(status, 202, r)
        jobs.run(r["task_ids"][0])
        result = next(v for v in self.ws()["creations"] if v["id"] == cid)
        self.assertEqual((result["revision"], result["data"]["goal"], result["data"]["image_asset_ids"]), (2,"reach",[image_id]))
        history = self.c.req(f"/api/creations/{cid}/revisions?project_id={self.p}")[1]
        self.assertNotIn("image_asset_ids", next(v["data"] for v in history if v["revision"] == 1))

        with D.db() as c:
            missing = "json_remove(data,'$.goal','$.image_asset_ids')"
            c.execute(f"UPDATE creation_outputs SET data={missing} WHERE id=?", (cid,))
            c.execute(f"UPDATE creation_revisions SET data={missing} WHERE creation_id=? AND revision=0", (cid,))
            row = c.execute("SELECT * FROM creation_outputs WHERE id=?", (cid,)).fetchone()
            self.assertEqual(jobs.rewrite_original(c, row)["image_asset_ids"], [image_id])
            c.execute("UPDATE tasks SET payload=json_remove(payload,'$.asset_snapshot','$.brief.goal') WHERE id=?", (row["task_id"],))
            unknown = jobs.rewrite_original(c, row)
            self.assertNotIn("goal", unknown)
            self.assertNotIn("image_asset_ids", unknown)

    def test_rechecks_sources_at_commit(self):
        cid = self.make_draft()
        source = "冷萃挂耳每包12克"
        with D.db() as c:
            row = c.execute("SELECT task_id,data FROM creation_outputs WHERE id=?", (cid,)).fetchone()
            draft = {**json.loads(row["data"]), "evidence":[{"asset_id":"temporary","quote":source}]}
            c.execute("UPDATE creation_outputs SET data=? WHERE id=?", (D.dumps(draft),cid))
        real_rewrite = adapters.rewrite
        def expire_during_rewrite(original, instruction, version, platform, demo, assets):
            self.assertIn(source, assets[0]["content"])
            result = real_rewrite(original, instruction, version, platform, demo, assets)
            with D.db() as c:
                c.execute("UPDATE tasks SET updated_at='2000-01-01T00:00:00+00:00' WHERE id=?", (row["task_id"],))
            return result
        status, r = self.post(f"/api/creations/{cid}/rewrite", {"revision":0, "instruction":"精简一下正文"})
        self.assertEqual(status, 202, r)
        with patch.object(adapters, "rewrite", side_effect=expire_during_rewrite):
            jobs.run(r["task_ids"][0])
        saved = next(v["data"] for v in self.ws()["creations"] if v["id"] == cid)
        self.assertEqual(saved["evidence"], draft["evidence"])
        self.assertTrue(any("文字依据" in issue for issue in saved["quality"]["issues"]))


if __name__ == "__main__":
    unittest.main()
