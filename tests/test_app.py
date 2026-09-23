"""Integration tests use an isolated database and never touch the user's workspace data."""

import unittest, tempfile, subprocess, os, socket, time, json, urllib.request, urllib.error, http.cookiejar, zipfile, io, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Client:
    def __init__(self, base):
        self.base = base
        self.http = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )

    def req(self, path, method="GET", data=None, raw=False):
        req = urllib.request.Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.http.open(req) as r:
                b = r.read()
                return r.status, b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db = str(Path(cls.tmp.name) / "test.db")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        cls.base = f"http://127.0.0.1:{port}"
        env = {
            **os.environ,
            "PORT": str(port),
            "DAOLOOK_DB": cls.db,
            "DAOLOOK_ADMIN_EMAIL": "admin@test.local",
            "DAOLOOK_ADMIN_PASSWORD": "integration-test-admin",
            "DAOLOOK_MODE": "demo",
        }
        cls.proc = subprocess.Popen(
            ["python3", "-m", "server.app"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(100):
            try:
                if Client(cls.base).req("/api/health")[0] == 200:
                    break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("Test server failed to start")
        cls.admin = Client(cls.base)
        assert (
            cls.admin.req(
                "/api/auth/login",
                "POST",
                {"email": "admin@test.local", "password": "integration-test-admin"},
            )[0]
            == 200
        )

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait()
        cls.tmp.cleanup()

    def setUp(self):
        self.c = Client(self.base)
        self.c.req("/api/auth/demo", "POST", {})
        self.boot = self.c.req("/api/bootstrap")[1]
        self.p = self.boot["projects"][0]["id"]
        self.ws = self.workspace()

    def workspace(self):
        return self.c.req("/api/workspace?project_id=" + self.p)[1]

    def post(self, path, d):
        return self.c.req(path, "POST", {"project_id": self.p, **d})

    def wait(self, ids):
        for _ in range(200):
            tasks = [t for t in self.c.req("/api/tasks")[1] if t["id"] in ids]
            if len(tasks) == len(ids) and all(
                t["state"] in ("SUCCEEDED", "FAILED", "CANCELLED") for t in tasks
            ):
                return tasks
            time.sleep(0.02)
        self.fail("Tasks did not complete")

    def test_malformed_admin_config_does_not_break_workers(self):
        for config in (
            {"limits": []},
            {"provider": "bad"},
            {"rules": {"analyze": True, "create": 15, "cover": 8}},
            {"limits": {"batch": 10, "timeout": 60, "retries": 1.5}},
        ):
            self.assertEqual(
                self.admin.req("/api/admin/config", "POST", config)[0], 400
            )

    def test_malformed_input_is_rejected_before_charging(self):
        for data in ([], "text", 123):
            self.assertEqual(self.c.req("/api/create", "POST", data)[0], 400)
        self.assertEqual(
            self.post(
                "/api/create",
                {
                    "source_id": self.ws["sources"][0]["id"],
                    "requirements": {"bad": "type"},
                },
            )[0],
            400,
        )
        self.assertEqual(
            self.post(
                "/api/create",
                {"source_id": self.ws["sources"][0]["id"], "temporary": float("nan")},
            )[0],
            400,
        )
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], 300)

    def test_auth_and_project_isolation(self):
        other = Client(self.base)
        other.req("/api/auth/demo", "POST", {})
        self.assertEqual(other.req("/api/workspace?project_id=" + self.p)[0], 404)
        self.assertEqual(
            other.req(
                "/api/create",
                "POST",
                {"project_id": self.p, "source_id": self.ws["sources"][0]["id"]},
            )[0],
            404,
        )
        self.assertEqual(self.c.req("/api/admin")[0], 403)
        self.assertEqual(Client(self.base).req("/api/tasks")[0], 401)
        status, p = self.c.req("/api/projects", "POST", {"name": "独立项目"})
        self.assertEqual(status, 200)
        self.assertEqual(
            self.c.req("/api/workspace?project_id=" + p["id"])[1]["sources"], []
        )

    def test_registration_login_logout(self):
        c = Client(self.base)
        email = f"{time.time_ns()}@test.local"
        self.assertEqual(
            c.req(
                "/api/auth/register",
                "POST",
                {"email": email, "password": "long-password"},
            )[0],
            200,
        )
        self.assertEqual(c.req("/api/auth/logout", "POST", {})[0], 200)
        self.assertEqual(c.req("/api/bootstrap")[0], 401)
        self.assertEqual(
            c.req(
                "/api/auth/login",
                "POST",
                {"email": email, "password": "incorrect-password"},
            )[0],
            401,
        )
        self.assertEqual(
            c.req(
                "/api/auth/login", "POST", {"email": email, "password": "long-password"}
            )[0],
            200,
        )

    def test_three_outputs_append_soft_delete_and_export(self):
        sid = self.ws["sources"][0]["id"]
        seen = set()
        for _ in range(2):
            status, r = self.post(
                "/api/create", {"source_id": sid, "requirements": "为独立咖啡店写作"}
            )
            self.assertEqual(status, 202)
            tasks = self.wait(r["task_ids"])
            self.assertEqual(tasks[0]["state"], "SUCCEEDED", tasks)
            ids = json.loads(tasks[0]["result"])["creation_ids"]
            self.assertEqual(len(ids), 3)
            self.assertFalse(seen.intersection(ids))
            seen.update(ids)
        self.assertEqual(len(self.workspace()["creations"]), 6)
        credits = self.c.req("/api/bootstrap")[1]["credits"]
        self.assertEqual(credits["balance"], 270)
        self.assertEqual(credits["frozen"], 0)
        target = next(iter(seen))
        self.assertEqual(
            self.c.req("/api/creations/" + target, "DELETE", {"project_id": self.p})[0],
            200,
        )
        self.assertEqual(len(self.workspace()["creations"]), 5)
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], 270)
        with sqlite3.connect(self.db) as conn:
            self.assertIsNotNone(
                conn.execute(
                    "SELECT deleted_at FROM creation_outputs WHERE id=?", (target,)
                ).fetchone()[0]
            )
        status, csv = self.c.req("/api/export?project_id=" + self.p, "GET", raw=True)
        self.assertEqual(status, 200)
        self.assertTrue(csv.startswith(b"\xef\xbb\xbf"))
        self.assertIn("稿件ID", csv.decode())
        status, xlsx = self.c.req(
            "/api/export?project_id=" + self.p + "&format=xlsx", raw=True
        )
        with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
            from xml.etree import ElementTree as ET

            root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
            self.assertEqual(len(list(root)[0]), 6)

    def test_platform_schemas_batch_and_validation(self):
        status, r = self.post(
            "/api/analyze",
            {
                "entry": "batch",
                "text": "https://www.xiaohongshu.com/explore/example\nhttps://v.douyin.com/example",
            },
        )
        self.assertEqual(status, 202)
        self.assertEqual(len(r["task_ids"]), 2)
        tasks = self.wait(r["task_ids"])
        self.assertTrue(all(t["state"] == "SUCCEEDED" for t in tasks), tasks)
        ids = {sid for t in tasks for sid in json.loads(t["result"])["source_ids"]}
        sources = [s for s in self.workspace()["sources"] if s["id"] in ids]
        for s in sources:
            self.assertEqual(len(s["analysis"]["sections"]), 10)
        dy = next(s for s in sources if s["platform"] == "douyin")
        self.assertIn("前三秒钩子", [s["name"] for s in dy["analysis"]["sections"]])
        self.assertEqual(
            self.post(
                "/api/analyze",
                {"entry": "single", "text": "https://evil.com/xiaohongshu.com"},
            )[0],
            400,
        )
        self.assertEqual(
            self.post(
                "/api/analyze",
                {"entry": "batch", "text": "\n".join(["https://xhslink.com/a"] * 11)},
            )[0],
            400,
        )

    def test_assets_update_and_delete(self):
        status, a = self.post(
            "/api/assets",
            {"name": "产品资料", "kind": "产品信息", "content": "真实产品信息"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(self.workspace()["assets"]), 1)
        self.assertEqual(
            self.c.req(
                "/api/assets/" + a["id"],
                "PATCH",
                {"project_id": self.p, "name": "更新资料", "content": "已更新"},
            )[0],
            200,
        )
        self.assertEqual(self.workspace()["assets"][0]["content"], "已更新")
        self.c.req("/api/assets/" + a["id"], "DELETE", {"project_id": self.p})
        self.assertEqual(self.workspace()["assets"], [])

    def test_cover_and_frozen_credits(self):
        r = self.post("/api/create", {"source_id": self.ws["sources"][0]["id"]})[1]
        t = self.wait(r["task_ids"])[0]
        cid = json.loads(t["result"])["creation_ids"][0]
        r = self.post("/api/cover", {"creation_id": cid, "direction": "极简文字"})[1]
        self.assertEqual(self.wait(r["task_ids"])[0]["state"], "SUCCEEDED")
        images = self.workspace()["images"]
        self.assertEqual(len(images), 1)
        self.assertTrue(
            images[0]["data"]["url"].startswith("data:image/svg+xml;base64,")
        )
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], 277)

    def test_cover_preview_validation_and_version_history(self):
        r = self.post("/api/create", {"source_id": self.ws["sources"][0]["id"]})[1]
        cid = json.loads(self.wait(r["task_ids"])[0]["result"])["creation_ids"][0]
        before = self.c.req("/api/bootstrap")[1]["credits"]["balance"]
        status, plan = self.post("/api/cover/plan", {"creation_id": cid})
        self.assertEqual(status, 200)
        self.assertEqual(len(plan["styles"]), 3)
        brief = {
            **plan["brief"],
            "style": "method",
            "title": "真实方法清单",
            "points": ["第一项方法", "第二项方法"],
        }
        self.assertEqual(
            self.post("/api/cover/preview", {"creation_id": cid, "brief": brief})[0],
            200,
        )
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], before)
        self.assertEqual(
            self.post(
                "/api/cover",
                {"creation_id": cid, "brief": {**brief, "style": "portrait"}},
            )[0],
            400,
        )
        self.assertEqual(
            self.post(
                "/api/cover/preview",
                {"creation_id": cid, "brief": {**brief, "asset_id": "not-owned"}},
            )[0],
            400,
        )
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], before)
        for title in ("第一版封面", "第二版封面"):
            status, task = self.post(
                "/api/cover", {"creation_id": cid, "brief": {**brief, "title": title}}
            )
            self.assertEqual(status, 202)
            self.assertEqual(self.wait(task["task_ids"])[0]["state"], "SUCCEEDED")
        images = self.workspace()["images"]
        self.assertEqual(len(images), 2)
        self.assertEqual(
            {im["data"]["brief"]["title"] for im in images},
            {"第一版封面", "第二版封面"},
        )
        self.assertEqual(
            self.c.req("/api/bootstrap")[1]["credits"]["balance"], before - 16
        )

    def test_uploaded_photo_flows_from_creation_into_cover(self):
        photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2uoAAAAASUVORK5CYII="
        status, asset = self.post(
            "/api/assets", {"name": "个人IP照片", "kind": "图片", "content": photo}
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            self.post(
                "/api/assets",
                {
                    "name": "坏图",
                    "kind": "图片",
                    "content": "data:image/png;base64,aGVsbG8=",
                },
            )[0],
            400,
        )
        self.assertEqual(
            self.post(
                "/api/create",
                {"source_id": self.ws["sources"][0]["id"], "assets": ["not-owned"]},
            )[0],
            400,
        )
        r = self.post(
            "/api/create",
            {"source_id": self.ws["sources"][0]["id"], "assets": [asset["id"]]},
        )[1]
        ids = json.loads(self.wait(r["task_ids"])[0]["result"])["creation_ids"]
        creations = self.workspace()["creations"]
        for c in creations:
            self.assertEqual(c["data"]["image_asset_ids"], [asset["id"]])
        plan = self.post("/api/cover/plan", {"creation_id": ids[0]})[1]
        self.assertEqual(plan["brief"]["asset_id"], asset["id"])
        brief = {**plan["brief"], "style": "method", "points": ["真实体验"]}
        status, preview = self.post(
            "/api/cover/preview", {"creation_id": ids[0], "brief": brief}
        )
        self.assertEqual(status, 200)
        import base64

        self.assertIn(photo, base64.b64decode(preview["url"].split(",")[1]).decode())
        task = self.post("/api/cover", {"creation_id": ids[0], "brief": brief})[1]
        self.assertEqual(self.wait(task["task_ids"])[0]["state"], "SUCCEEDED")
        self.c.req("/api/assets/" + asset["id"], "DELETE", {"project_id": self.p})
        saved = self.workspace()["images"][0]["data"]
        self.assertIn(photo, base64.b64decode(saved["url"].split(",")[1]).decode())
        plan = self.post("/api/cover/plan", {"creation_id": ids[0]})[1]
        self.assertEqual(plan["brief"]["asset_id"], "")

    def test_failure_refunds_once(self):
        self.admin.req("/api/admin/config", "POST", {"mode": "live"})
        try:
            status, r = self.post(
                "/api/analyze",
                {"entry": "single", "text": "https://xhslink.com/example"},
            )
            self.assertEqual(status, 202)
            t = self.wait(r["task_ids"])[0]
            self.assertEqual(t["state"], "FAILED")
            credits = self.c.req("/api/bootstrap")[1]["credits"]
            self.assertEqual(credits["balance"], 300)
            self.assertEqual(credits["frozen"], 0)
            logs = self.c.req("/api/credits")[1]
            self.assertEqual(len([l for l in logs if l["kind"] == "REFUND"]), 1)
        finally:
            self.admin.req("/api/admin/config", "POST", {"mode": "demo"})

    def test_insufficient_credits_no_partial_writes(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "UPDATE credit_accounts SET balance=1 WHERE user_id=?",
                (self.boot["user"]["id"],),
            )
        status, _ = self.post("/api/create", {"source_id": self.ws["sources"][0]["id"]})
        self.assertEqual(status, 400)
        self.assertEqual(self.c.req("/api/tasks")[1], [])
        self.assertEqual(self.workspace()["creations"], [])

    def test_admin_skill_lifecycle_and_grant(self):
        self.assertEqual(
            self.admin.req(
                "/api/admin/grant",
                "POST",
                {"user_id": self.boot["user"]["id"], "amount": 50},
            )[0],
            200,
        )
        self.assertEqual(self.c.req("/api/bootstrap")[1]["credits"]["balance"], 350)
        self.admin.req(
            "/api/admin/skills",
            "POST",
            {"name": "xhs_analysis", "prompt": "测试提示词，使用真实依据"},
        )
        skills = self.admin.req("/api/admin")[1]["skills"]
        s = next(s for s in skills if s["status"] == "Draft")
        self.assertEqual(
            self.admin.req(
                "/api/admin/skills/state",
                "POST",
                {"id": s["id"], "status": "Published"},
            )[0],
            400,
        )
        self.assertEqual(
            self.admin.req(
                "/api/admin/skills/state", "POST", {"id": s["id"], "status": "Test"}
            )[0],
            200,
        )
        self.assertEqual(
            self.admin.req(
                "/api/admin/skills/state",
                "POST",
                {"id": s["id"], "status": "Published"},
            )[0],
            200,
        )

    def test_model_provider_routes_and_key_masking(self):
        status, result = self.admin.req(
            "/api/admin/provider",
            "POST",
            {
                "name": "test provider",
                "base_url": "https://model.example/v1",
                "api_key": "synthetic-test-key",
                "enabled": True,
            },
        )
        self.assertEqual(status, 200)
        provider_id = result["id"]
        admin = self.admin.req("/api/admin")[1]
        provider = next(p for p in admin["providers"] if p["id"] == provider_id)
        self.assertEqual(provider["api_key"], "••••••••")
        routes = admin["routes"]
        routes["create"] = {
            "primary": {"provider": provider_id, "model": "main-model"},
            "backup": {"provider": "default", "model": "backup-model"},
        }
        self.assertEqual(self.admin.req("/api/admin/routes", "POST", routes)[0], 200)
        self.assertEqual(
            self.admin.req("/api/admin")[1]["routes"]["create"]["primary"]["provider"],
            provider_id,
        )
        routes["create"]["primary"]["provider"] = "nonexistent"
        self.assertEqual(self.admin.req("/api/admin/routes", "POST", routes)[0], 400)
        self.assertEqual(self.c.req("/api/admin/provider", "POST", provider)[0], 403)

    def test_invalid_config_rolls_back_all_fields(self):
        old = self.admin.req("/api/admin")[1]["config"]["mode"]
        status, _ = self.admin.req(
            "/api/admin/config",
            "POST",
            {"mode": "live", "rules": {"analyze": -5, "create": 15, "cover": 8}},
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.admin.req("/api/admin")[1]["config"]["mode"], old)
        ledger = self.admin.req("/api/admin/ledger?user_id=" + self.boot["user"]["id"])[
            1
        ]
        self.assertEqual(ledger[0]["kind"], "GRANT")


if __name__ == "__main__":
    unittest.main(verbosity=2)
