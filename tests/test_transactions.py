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

    def source_id(self):
        with D.db() as c:
            return c.execute("SELECT id FROM source_contents LIMIT 1").fetchone()[0]

    def test_duplicate_worker_claim_and_settlement_are_atomic(self):
        from threading import Event

        entered, release = Event(), Event()
        real_create = jobs.adapters.create

        def delayed(*args, **kwargs):
            entered.set()
            if not release.wait(5):
                raise RuntimeError("test gate timed out")
            return real_create(*args)

        ident = jobs.submit(
            self.user, self.project, "create", {"source_id": self.source_id()}
        )
        with patch.object(jobs.adapters, "create", side_effect=delayed) as create:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(jobs.run, ident)
                try:
                    self.assertTrue(entered.wait(3))
                    pool.submit(jobs.run, ident).result(timeout=3)
                finally:
                    release.set()
                first.result(timeout=3)
            self.assertEqual(create.call_count, 1)
        with D.db() as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM creation_outputs").fetchone()[0], 8
            )
            self.assertEqual(
                tuple(
                    c.execute("SELECT balance,frozen FROM credit_accounts").fetchone()
                ),
                (285, 0),
            )
            self.assertEqual(
                c.execute(
                    "SELECT count(*) FROM credit_ledger WHERE kind='SETTLE'"
                ).fetchone()[0],
                1,
            )

    def test_late_result_after_refund_never_settles(self):
        for terminal in ("fail", "cancel"):
            ident = jobs.submit(
                self.user, self.project, "create", {"source_id": self.source_id()}
            )
            real_create = jobs.adapters.create

            def delayed(*args, **kwargs):
                jobs.fail(ident, "expired") if terminal == "fail" else jobs.cancel(
                    ident, self.user
                )
                return real_create(*args)

            with patch.object(jobs.adapters, "create", side_effect=delayed):
                jobs.run(ident)
        with D.db() as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM creation_outputs").fetchone()[0], 0
            )
            self.assertEqual(
                tuple(
                    c.execute("SELECT balance,frozen FROM credit_accounts").fetchone()
                ),
                (300, 0),
            )

    def test_assets_are_snapshotted_at_submission(self):
        aid = D.uid()
        with D.db() as c:
            c.execute(
                "INSERT INTO assets VALUES (?,?,?,?,?,?)",
                (aid, self.project, "品牌", "品牌资料", "提交时的资料", D.now()),
            )
        ident = jobs.submit(
            self.user,
            self.project,
            "create",
            {"source_id": self.source_id(), "assets": [aid]},
        )
        with D.db() as c:
            c.execute("DELETE FROM assets WHERE id=?", (aid,))
        with patch.object(
            jobs.adapters, "create", wraps=jobs.adapters.create
        ) as create:
            jobs.run(ident)
            self.assertEqual(create.call_args.args[1][0]["content"], "提交时的资料")

    def test_model_cannot_forge_source_metrics(self):
        ident = jobs.submit(
            self.user, self.project, "analyze", {"text": "example", "entry": "single"}
        )
        with patch.object(
            jobs.adapters,
            "analyze",
            return_value=(
                {
                    "sections": [],
                    "source": {"likes": 999999999, "demo": False, "platform": "evil"},
                },
                "fake",
            ),
        ):
            jobs.run(ident)
        with D.db() as c:
            result = json.loads(
                c.execute("SELECT result FROM tasks WHERE id=?", (ident,)).fetchone()[0]
            )
            source = json.loads(
                c.execute(
                    "SELECT data FROM source_contents WHERE id=?",
                    (result["source_ids"][0],),
                ).fetchone()[0]
            )
            self.assertNotEqual(source["likes"], 999999999)
            self.assertTrue(source["demo"])
            self.assertEqual(source["platform"], "xhs")

    def test_project_owner_checked_inside_credit_transaction(self):
        other = new_user("another@local.test", demo=True)
        with self.assertRaises(ValueError):
            jobs.submit(other, self.project, "analyze", {})
        with D.db() as c:
            self.assertEqual(
                tuple(
                    c.execute(
                        "SELECT balance,frozen FROM credit_accounts WHERE user_id=?",
                        (other,),
                    ).fetchone()
                ),
                (300, 0),
            )

    def test_deleted_creation_cannot_receive_late_cover(self):
        sid = self.source_id()
        creation_task = jobs.submit(
            self.user, self.project, "create", {"source_id": sid}
        )
        jobs.run(creation_task)
        with D.db() as c:
            cid = c.execute("SELECT id FROM creation_outputs LIMIT 1").fetchone()[0]
        ident = jobs.submit(
            self.user,
            self.project,
            "cover",
            {"source_id": sid, "creation_id": cid, "prepared": {"test": True}},
        )

        def render(*args, **kwargs):
            with D.db() as c:
                c.execute(
                    "UPDATE creation_outputs SET deleted_at=? WHERE id=?",
                    (D.now(), cid),
                )
            return {"demo": True, "url": "test"}

        with patch.object(jobs.covers, "render", side_effect=render):
            with self.assertRaises(ValueError):
                jobs.run(ident)
        jobs.fail(ident, "稿件已删除")
        with D.db() as c:
            self.assertEqual(
                c.execute("SELECT count(*) FROM generated_images").fetchone()[0], 0
            )
            self.assertEqual(
                tuple(
                    c.execute("SELECT balance,frozen FROM credit_accounts").fetchone()
                ),
                (285, 0),
            )

    def test_queued_demo_does_not_switch_to_paid_live_fetch(self):
        ident = jobs.submit(
            self.user, self.project, "analyze", {"text": "example", "entry": "single"}
        )
        with D.db() as c:
            c.execute(
                "UPDATE settings SET value=? WHERE key='mode'", (D.dumps("live"),)
            )
        with patch.object(
            jobs.adapters.TikHubAdapter,
            "getContentDetail",
            side_effect=AssertionError("must not fetch"),
        ):
            jobs.run(ident)
        with D.db() as c:
            self.assertEqual(
                c.execute("SELECT state FROM tasks WHERE id=?", (ident,)).fetchone()[0],
                "SUCCEEDED",
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
