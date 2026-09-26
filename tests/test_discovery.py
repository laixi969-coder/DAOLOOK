"""博主/关键词入口：解析、基线、精选排序、逐条结算与 PARTIAL。"""

import importlib, json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
from server import discovery, jobs, ranking
from server.app import new_user

D = importlib.import_module("server.db")
NOW = int(time.time())


def xhs_search(stats):
    return {
        "data": {
            "items": [
                {
                    "note": {
                        "id": f"n{i}",
                        "title": f"笔记{i}",
                        "timestamp": NOW - 86400 * (i + 1),
                        "user": {"fans": "1.2万"},
                        "interact_info": {
                            "liked_count": likes,
                            "collected_count": saves,
                            "comment_count": 0,
                        },
                    }
                }
                for i, (likes, saves) in enumerate(stats)
            ]
        }
    }


class ParseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / "db.sqlite")
        D.init()

    def tearDown(self):
        D.DB_PATH = self.original
        self.temp.cleanup()

    def test_counts_and_time(self):
        self.assertEqual(discovery.parse_count("1.2万"), 12000)
        self.assertEqual(discovery.parse_count("10万+"), 100000)
        self.assertEqual(discovery.parse_count("3.4w"), 34000)
        self.assertEqual(discovery.parse_count("1,234"), 1234)
        self.assertIsNone(discovery.parse_count("很多"))
        self.assertIsNone(discovery.parse_count(True))
        self.assertAlmostEqual(
            discovery.parse_age_days({"create_time": NOW - 86400 * 2}, NOW), 2
        )
        self.assertAlmostEqual(
            discovery.parse_age_days({"time": (NOW - 86400) * 1000}, NOW), 1
        )
        self.assertIsNone(discovery.parse_age_days({"create_time": 12}, NOW))
        self.assertIsNone(discovery.parse_age_days({}, NOW))

    def test_list_items_and_baseline(self):
        items = discovery.list_items(xhs_search([(10, 0), (500, 100), (30, 5)]), "xhs")
        self.assertEqual([i["id"] for i in items], ["n0", "n1", "n2"])
        self.assertEqual(items[1]["likes"], 500)
        self.assertEqual(items[1]["followers"], 12000)
        self.assertAlmostEqual(items[0]["age_days"], 1, places=1)
        self.assertEqual(discovery.baseline(items), 40)
        self.assertEqual(ranking.median([1, None, 3, 2]), 2)

    def test_douyin_items(self):
        raw = {
            "aweme_list": [
                {
                    "aweme_id": "a1",
                    "desc": "x",
                    "create_time": NOW - 3600,
                    "statistics": {"digg_count": 9, "collect_count": 1},
                    "author": {"follower_count": 100},
                }
            ]
        }
        item = discovery.list_items(raw, "douyin")[0]
        self.assertEqual(item["url"], "https://www.douyin.com/video/a1")
        self.assertEqual((item["likes"], item["followers"]), (9, 100))

    def test_pick_prefers_relative_outliers(self):
        items = discovery.list_items(
            xhs_search([(10, 0), (500, 100), (30, 5), (0, 0)]), "xhs"
        )
        chosen = discovery.pick(items, 2, "category_median", discovery.baseline(items))
        self.assertEqual(chosen[0]["id"], "n1")
        self.assertEqual(len(chosen), 2)
        self.assertEqual(chosen[0]["selection"]["pool"], 4)
        self.assertEqual(chosen[0]["selection"]["rank_source"], 2)


class DiscoveryJobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / "db.sqlite")
        D.init()
        with D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        self.user = new_user("d@local.test", demo=True)
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

    def account(self):
        with D.db() as c:
            return tuple(
                c.execute(
                    "SELECT balance,frozen FROM credit_accounts WHERE user_id=?",
                    (self.user,),
                ).fetchone()
            )

    def run_keyword(self, fail_urls):
        raw = xhs_search([(10, 0), (500, 100), (30, 5), (80, 1), (2, 0)])

        def detail(self_, url, p):
            if url in fail_urls:
                raise ValueError("笔记不可见")
            ident = url.rsplit("/", 1)[1]
            return {
                "platform": p,
                "url": url,
                "demo": False,
                "title": ident,
                "body": ident,
                "likes": 1,
                "saves": 0,
                "comments": 0,
                "followers": None,
                "age_days": None,
            }

        start = self.account()[0]
        ident = jobs.submit(
            self.user, self.project, "analyze", {"text": "咖啡", "entry": "keyword"}
        )
        self.assertEqual(self.account(), (start - 15, 15))
        with (
            patch.object(jobs.adapters.TikHubAdapter, "searchContents", return_value=raw),
            patch.object(jobs.adapters.TikHubAdapter, "getContentDetail", detail),
            patch.object(
                jobs.adapters, "analyze", return_value=({"sections": []}, "m")
            ),
        ):
            jobs.run(ident)
        with D.db() as c:
            task = dict(c.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone())
            sources = [
                json.loads(r[0])
                for r in c.execute(
                    "SELECT data FROM source_contents ORDER BY rowid"
                )
            ]
        sources = [s for s in sources if not s.get("demo")]
        return start, task, sources

    def test_keyword_picks_by_score_and_sets_baseline(self):
        start, task, sources = self.run_keyword(set())
        self.assertEqual(task["state"], "SUCCEEDED")
        self.assertEqual(task["cost"], 15)
        self.assertEqual(self.account(), (start - 15, 0))
        self.assertEqual(
            [s["title"] for s in sources], ["n1", "n3", "n2"]
        )
        self.assertTrue(all(s["category_median"] == 40 for s in sources))
        self.assertTrue(all(s["followers"] == 12000 for s in sources))
        self.assertTrue(all(s["age_days"] is not None for s in sources))

    def test_partial_failure_refunds_per_item(self):
        start, task, sources = self.run_keyword(
            {"https://www.xiaohongshu.com/explore/n3"}
        )
        self.assertEqual(task["state"], "PARTIAL")
        self.assertEqual(task["cost"], 10)
        self.assertEqual(len(sources), 2)
        self.assertEqual(self.account(), (start - 10, 0))
        self.assertEqual(len(json.loads(task["result"])["failures"]), 1)
        with D.db() as c:
            kinds = [
                r[0]
                for r in c.execute(
                    "SELECT kind FROM credit_ledger WHERE task_id=? ORDER BY created_at",
                    (task["id"],),
                )
            ]
        self.assertIn("REFUND", kinds)

    def test_all_failed_raises_for_full_refund(self):
        with self.assertRaisesRegex(ValueError, "精选内容均未能完成拆解"):
            self.run_keyword(
                {f"https://www.xiaohongshu.com/explore/n{i}" for i in range(5)}
            )


if __name__ == "__main__":
    unittest.main()
