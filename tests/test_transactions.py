import unittest, tempfile, importlib, json
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from server import jobs, maintenance
from server.app import new_user

D = importlib.import_module("server.db")


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / "db.sqlite")
        D.init()
        self.user = new_user("test@local.test", demo=True)
        with D.db() as c:
            self.project = c.execute(
                "SELECT id FROM projects WHERE user_id=?", (self.user,)
            ).fetchone()[0]
        self.queue = patch.object(jobs.Q, "put")
        self.queue.start()

    def tearDown(self):
        self.queue.stop()
        D.DB_PATH = self.original
        self.temp.cleanup()

    def test_concurrent_freezes_never_overdraw(self):
        with D.db() as c:
            c.execute(
                "UPDATE credit_accounts SET balance=20 WHERE user_id=?", (self.user,)
            )

        def submit(_):
            try:
                return jobs.submit(self.user, self.project, "create", {})
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=5) as pool:
            ids = list(pool.map(submit, range(5)))
        self.assertEqual(len([x for x in ids if x]), 1)
        with D.db() as c:
            account = c.execute(
                "SELECT balance,frozen FROM credit_accounts WHERE user_id=?",
                (self.user,),
            ).fetchone()
        self.assertEqual(tuple(account), (5, 15))

    def test_batch_is_atomic(self):
        with D.db() as c:
            c.execute(
                "UPDATE credit_accounts SET balance=9 WHERE user_id=?", (self.user,)
            )
        with self.assertRaises(ValueError):
            jobs.submit_many(self.user, self.project, "analyze", [{}, {}])
        with D.db() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM tasks").fetchone()[0], 0)
            self.assertEqual(
                c.execute("SELECT balance FROM credit_accounts").fetchone()[0], 9
            )

    def test_cancel_then_failure_does_not_refund_twice(self):
        ident = jobs.submit(self.user, self.project, "create", {})
        jobs.cancel(ident, self.user)
        jobs.fail(ident, "late failure")
        jobs.state(ident, "GENERATING")
        with D.db() as c:
            account = c.execute("SELECT balance,frozen FROM credit_accounts").fetchone()
            self.assertEqual(tuple(account), (300, 0))
            self.assertEqual(
                c.execute("SELECT state FROM tasks").fetchone()[0], "CANCELLED"
            )
            self.assertEqual(
                c.execute(
                    "SELECT count(*) FROM credit_ledger WHERE kind='REFUND'"
                ).fetchone()[0],
                1,
            )

    def test_success_is_not_refunded(self):
        with D.db() as c:
            sid = c.execute("SELECT id FROM source_contents LIMIT 1").fetchone()[0]
        ident = jobs.submit(self.user, self.project, "create", {"source_id": sid})
        jobs.run(ident)
        jobs.fail(ident, "late failure")
        with D.db() as c:
            self.assertEqual(
                c.execute("SELECT balance FROM credit_accounts").fetchone()[0], 285
            )

    def test_temporary_material_expires_but_assets_remain(self):
        ident = jobs.submit(
            self.user, self.project, "create", {"temporary": "一次性内容"}
        )
        jobs.fail(ident, "test")
        with D.db() as c:
            c.execute(
                "UPDATE tasks SET updated_at=? WHERE id=?",
                ("2020-01-01T00:00:00+00:00", ident),
            )
            c.execute(
                "INSERT INTO assets VALUES (?,?,?,?,?,?)",
                (D.uid(), self.project, "长期资料", "品牌资料", "永久保留", D.now()),
            )
        maintenance.cleanup()
        with D.db() as c:
            payload = json.loads(c.execute("SELECT payload FROM tasks").fetchone()[0])
            self.assertEqual(payload["temporary"], "")
            self.assertTrue(payload["temporary_expired"])
            self.assertEqual(
                c.execute("SELECT content FROM assets").fetchone()[0], "永久保留"
            )


if __name__ == "__main__":
    unittest.main()
