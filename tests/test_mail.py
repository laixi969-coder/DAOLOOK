"""邮箱验证码：注册验证、找回密码、次数/过期限制与不暴露邮箱是否注册。"""

import importlib, json, tempfile, threading, time, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

D = importlib.import_module("server.db")
from server import mailer, app
from tests.test_app import Client

MAIL = {
    "enabled": True,
    "host": "smtp.example.com",
    "port": 465,
    "security": "ssl",
    "username": "u",
    "password": "p",
    "sender": "DAOLOOK <no-reply@example.com>",
}


class MailFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / "db.sqlite")
        D.init()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        app.RATE.clear()
        self.sent = []
        self.patch = patch.object(
            mailer, "send_mail", side_effect=lambda to, subj, text: self.sent.append((to, text))
        )
        self.patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.c = Client(f"http://127.0.0.1:{self.server.server_address[1]}")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.patch.stop()
        D.DB_PATH = self.original
        self.temp.cleanup()

    def enable(self):
        with D.db() as c:
            c.execute("UPDATE settings SET value=? WHERE key='mail'", (json.dumps(MAIL),))

    def code(self):
        return self.sent[-1][1].split("验证码是 ")[1][:6]

    def test_disabled_keeps_plain_register_and_blocks_reset(self):
        self.assertFalse(self.c.req("/api/public")[1]["mail"])
        status, _ = self.c.req(
            "/api/auth/register", "POST", {"email": "a@x.com", "password": "12345678"}
        )
        self.assertEqual(status, 200)
        status, body = self.c.req(
            "/api/auth/code", "POST", {"email": "a@x.com", "purpose": "reset"}
        )
        self.assertEqual(status, 400)
        self.assertIn("管理员", body["error"])

    def test_register_requires_valid_code(self):
        self.enable()
        self.assertTrue(self.c.req("/api/public")[1]["mail"])
        creds = {"email": "b@x.com", "password": "12345678"}
        self.assertEqual(self.c.req("/api/auth/register", "POST", creds)[0], 400)
        self.assertEqual(
            self.c.req("/api/auth/code", "POST", {"email": "b@x.com", "purpose": "register"})[0],
            200,
        )
        # 60 秒内不能重发
        self.assertEqual(
            self.c.req("/api/auth/code", "POST", {"email": "b@x.com", "purpose": "register"})[0],
            400,
        )
        self.assertEqual(
            self.c.req("/api/auth/register", "POST", {**creds, "code": "000000" if self.code() != "000000" else "111111"})[0],
            400,
        )
        self.assertEqual(
            self.c.req("/api/auth/register", "POST", {**creds, "code": self.code()})[0], 200
        )
        # 验证码一次性
        with D.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM email_codes").fetchone())

    def test_reset_password_flow(self):
        self.c.req("/api/auth/register", "POST", {"email": "r@x.com", "password": "12345678"})
        self.enable()
        # 未注册邮箱：返回成功但不发信
        self.assertEqual(
            self.c.req("/api/auth/code", "POST", {"email": "nobody@x.com", "purpose": "reset"})[0],
            200,
        )
        self.assertEqual(self.sent, [])
        self.c.req("/api/auth/code", "POST", {"email": "r@x.com", "purpose": "reset"})
        status, _ = self.c.req(
            "/api/auth/reset",
            "POST",
            {"email": "r@x.com", "code": self.code(), "password": "new-password-1"},
        )
        self.assertEqual(status, 200)
        fresh = Client(self.c.base)
        self.assertEqual(
            fresh.req("/api/auth/login", "POST", {"email": "r@x.com", "password": "12345678"})[0],
            401,
        )
        self.assertEqual(
            fresh.req("/api/auth/login", "POST", {"email": "r@x.com", "password": "new-password-1"})[0],
            200,
        )

    def test_attempt_limit_and_expiry(self):
        self.enable()
        mailer.issue("t@x.com", "reset")
        good = self.code()
        bad = "000000" if good != "000000" else "111111"
        for _ in range(mailer.MAX_ATTEMPTS):
            with self.assertRaisesRegex(ValueError, "不正确"):
                mailer.verify("t@x.com", "reset", bad)
        with self.assertRaisesRegex(ValueError, "次数过多"):
            mailer.verify("t@x.com", "reset", good)
        with D.db() as c:
            c.execute("DELETE FROM email_codes")
        mailer.issue("t@x.com", "reset")
        with D.db() as c:
            c.execute("UPDATE email_codes SET expires=?", (time.time() - 1,))
        with self.assertRaisesRegex(ValueError, "过期"):
            mailer.verify("t@x.com", "reset", self.code())

    def test_send_failure_does_not_leave_code(self):
        self.enable()
        self.patch.stop()
        with patch.object(mailer, "send_mail", side_effect=OSError("smtp down")):
            with self.assertRaisesRegex(ValueError, "发送失败"):
                mailer.issue("f@x.com", "register")
        self.patch.start()
        with D.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM email_codes").fetchone())


if __name__ == "__main__":
    unittest.main()
