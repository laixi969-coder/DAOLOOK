"""后台：注册白名单、新用户赠送积分、积分发放与扣减。"""

import importlib, os, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

D = importlib.import_module("server.db")
from server import app, jobs
from tests.test_app import Client

PASSWORD = "signup-test-password"


class SignupAdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / "db.sqlite")
        D.init()
        app.RATE.clear()
        self.env = patch.dict(os.environ, {"DAOLOOK_ADMIN_EMAIL": "boss@test.local"})
        self.env.start()
        self.queue = patch.object(jobs.Q, "put")
        self.queue.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        app.new_user("boss@test.local", PASSWORD, "admin")
        self.admin = Client(self.base)
        status, _ = self.admin.req(
            "/api/auth/login", "POST", {"email": "boss@test.local", "password": PASSWORD}
        )
        self.assertEqual(status, 200)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.queue.stop()
        self.env.stop()
        D.DB_PATH = self.original
        self.temp.cleanup()

    def register(self, email):
        app.RATE.clear()
        c = Client(self.base)
        status, body = c.req("/api/auth/register", "POST", {"email": email, "password": PASSWORD})
        return status, body, c

    def config(self, signup):
        return self.admin.req("/api/admin/config", "POST", {"signup": signup})

    def user(self, email):
        users = self.admin.req("/api/admin")[1]["users"]
        return next(u for u in users if u["email"] == email)

    def test_default_open_signup_with_100_credits(self):
        status, _, c = self.register("new@test.local")
        self.assertEqual(status, 200)
        self.assertEqual(c.req("/api/bootstrap")[1]["credits"]["balance"], 100)
        self.assertFalse(self.admin.req("/api/public")[1]["whitelist"])

    def test_whitelist_blocks_unlisted_and_normalizes_emails(self):
        status, _ = self.config(
            {"whitelist": True, "emails": [" Invited@Test.local ", "invited@test.local", ""], "welcome_credits": 0}
        )
        self.assertEqual(status, 200)
        signup = self.admin.req("/api/admin")[1]["config"]["signup"]
        self.assertEqual(signup["emails"], ["invited@test.local"])
        self.assertTrue(self.admin.req("/api/public")[1]["whitelist"])
        status, body, _ = self.register("stranger@test.local")
        self.assertEqual(status, 403)
        self.assertIn("白名单", body["error"])
        status, _, c = self.register("INVITED@test.local")
        self.assertEqual(status, 200)
        self.assertEqual(c.req("/api/bootstrap")[1]["credits"]["balance"], 0)
        with D.db() as conn:
            self.assertEqual(
                conn.execute(
                    "SELECT count(*) FROM credit_ledger l JOIN users u ON u.id=l.user_id WHERE u.email='invited@test.local'"
                ).fetchone()[0],
                0,
            )
        # 验证码入口同样拦截
        app.RATE.clear()
        status, _ = Client(self.base).req(
            "/api/auth/code", "POST", {"email": "stranger@test.local", "purpose": "register"}
        )
        self.assertEqual(status, 403)

    def test_admin_email_always_allowed(self):
        self.config({"whitelist": True, "emails": [], "welcome_credits": 100})
        with D.db() as c:
            c.execute("DELETE FROM sessions")
            c.execute("DELETE FROM credit_ledger")
            c.execute("DELETE FROM projects")
            c.execute("DELETE FROM credit_accounts")
            c.execute("DELETE FROM users")
        self.assertEqual(self.register("boss@test.local")[0], 200)

    def test_invalid_signup_settings_rejected(self):
        for bad in (
            {"whitelist": True, "emails": ["not-an-email"], "welcome_credits": 0},
            {"whitelist": True, "emails": [], "welcome_credits": -1},
            {"whitelist": True, "emails": "a@b.cn", "welcome_credits": 0},
        ):
            self.assertEqual(self.config(bad)[0], 400, bad)

    def test_grant_and_deduct_with_ledger(self):
        _, _, c = self.register("user@test.local")
        uid = self.user("user@test.local")["id"]
        grant = lambda amount, note="": self.admin.req(
            "/api/admin/grant", "POST", {"user_id": uid, "amount": amount, "note": note}
        )
        self.assertEqual(grant(50)[0], 200)
        self.assertEqual(grant(-30, "发错了")[0], 200)
        self.assertEqual(c.req("/api/bootstrap")[1]["credits"]["balance"], 120)
        status, body = grant(-121)
        self.assertEqual(status, 400)
        self.assertIn("120", body["error"])
        for bad in (0, 100001, -100001, 1.5, "10"):
            self.assertEqual(grant(bad)[0], 400, bad)
        rows = self.admin.req(f"/api/admin/ledger?user_id={uid}")[1]
        deduct = next(r for r in rows if r["kind"] == "DEDUCT")
        self.assertEqual(deduct["amount"], -30)
        self.assertEqual(deduct["description"], "管理员扣减：发错了")
        self.assertEqual(c.req("/api/bootstrap")[1]["credits"]["balance"], 120)

    def test_non_admin_cannot_adjust(self):
        _, _, c = self.register("user@test.local")
        uid = self.user("user@test.local")["id"]
        status, _ = c.req("/api/admin/grant", "POST", {"user_id": uid, "amount": 500})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
