import concurrent.futures
import datetime
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import calibrate_ranking as cal, review_references as review
from server import catalog, discovery, overseas_daily, overseas_editions, overseas_feed, overseas_library, overseas_visuals, ranking

D = importlib.import_module("server.db")


class EvidenceSortTests(unittest.TestCase):
    def test_measured_zero_precedes_freshness_and_benchmark_excludes_unverified(self):
        data = [{"id":"no-metrics","age_days":1,"title":"A"}, {"id":"zero","likes":0,"title":"B"},
                {"id":"measured","likes":1000,"saves":100,"comments":50,"followers":1000,"age_days":1,"title":"C"}]
        with patch.object(ranking, "setting", return_value=cal.DEFAULT):
            result = discovery.pick(data, 3, "category_median", discovery.baseline(data))
            self.assertEqual([c["id"] for c in result], ["measured","zero","no-metrics"])
            self.assertIsNone(result[2]["selection"]["score"])
            self.assertEqual(result[2]["selection"]["evidence_status"],"needs_metrics")
            reasons = catalog.evidence({**result[2], "origin":{"entry":"keyword"}},ranking.score(data[0]))
            self.assertIn("待核实候选", reasons[0])
            examples = discovery.benchmark_from(data,"开店","test")
            self.assertEqual([x["title"] for x in examples["examples"]],["C","B"])
            self.assertEqual(examples["unverified_count"],1)

    def test_holdout_uses_whole_groups_and_borrow_labels(self):
        rows = [dict(label=0, borrow=0, batch="train", split="A", content=dict(url="duplicate",likes=10)),
                dict(label=1, borrow=2, batch="train", split="A", content=dict(url="train",likes=20))]
        for n, (likes, borrow) in enumerate(((None,0),(1,1),(2,2),(9,1))):
            rows.append(dict(label=0, borrow=borrow, batch="later", split="B",
                             content=dict(url=f"item{n}" if n else "duplicate",likes=likes,age_days=1)))
        train, held = cal.partition(rows,["B"])
        self.assertEqual([r["content"]["url"] for r in train], ["train"])
        report = cal.top_three(held,{"current":cal.DEFAULT})
        self.assertEqual(report["source_order"]["borrowable"],2)
        self.assertEqual(report["current"]["borrowable"],3)
        self.assertLess(report["source_order"]["ndcg_at_3"],report["likes"]["ndcg_at_3"])
        held[0]["borrow"] = None
        self.assertIsNone(cal.top_three(held,{"current":cal.DEFAULT})["current"]["precision_at_3"])
        rows[0]["batch"] = "later"
        with self.assertRaises(ValueError): cal.partition(rows, ["B"])


class ReviewedReferences(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(D,'DB_PATH',str(Path(self.tmp.name)/'db'))
        patcher.start()
        self.addCleanup(patcher.stop)
        D.init()
        self.stamp = '2026-11-24T15:00:00+00:00'
        self.url = 'https://www.youtube.com/watch?v=01234567890'
        self.item = {'id':'feed_0123456','platform':'youtube','url':self.url,'publisher':'Test','title':'Store tour',
                     'summary':'We are open.', 'source_kind':'daily_feed', 'published_at':self.stamp}
        with D.db() as c:
            c.execute('INSERT INTO overseas_feed_videos VALUES (?,?,?,?,?,?)',
                      (self.item['id'],self.url,json.dumps(self.item),self.stamp,self.stamp,self.stamp))
        self.evidence = {'second':3.5,'change':'纸盒转过来露出地址','props':'纸盒、手机','method':'同一机位转动纸盒','mechanism':'翻面指路','title_zh':'纸盒转个面，店址出现了'}

    def test_operator_review_reaches_daily_and_reference_and_survives_pruning(self):
        day = datetime.date(2026,11,24)
        with D.db() as c:
            self.assertEqual(review.sample(c,'unmatched',day,14,1,'s')[0]['url'],self.url)
            with self.assertRaises(ValueError): review.record(c,'https://example.com','keep',self.evidence,self.stamp)
            with self.assertRaises(ValueError): review.record(c,self.url,'keep',{'second':0},self.stamp)
            review.record(c,self.url,'keep',self.evidence,self.stamp)
            review.record(c,self.url,'keep',self.evidence,self.stamp)
            self.assertEqual(review.sample(c,'unmatched',day,14,1,'s'),[])
            edition = overseas_daily.select(c,self.stamp,True)
            self.assertEqual(edition['picks'][0]['url'],self.url)
            self.assertEqual(edition['picks'][0]['new_match'],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM overseas_match_events').fetchone()[0],1)
        with patch.object(overseas_feed,'now',return_value=self.stamp):
            card = overseas_library.recommendations('',scope='today')[0]
            self.assertEqual(card['filming'],self.evidence['method'])
            self.assertEqual(card['title_zh'], self.evidence['title_zh'])
            self.assertIn('3.5 秒', card['filming_basis'])
            saved = overseas_library.reference('',card['creation_reference_id'])
            self.assertEqual(saved['idea_zh'],self.evidence['change'])
            self.assertEqual(saved['title_zh'],self.evidence['title_zh'])
        with D.db() as c:
            c.execute('DELETE FROM overseas_feed_videos')
            stats = review.report(c,day,14)
            self.assertEqual(stats['days'][-1]['first_matches_recorded'],1)
            self.assertEqual(stats['reviewed'],1)
            self.assertEqual(stats['shootable_rate'],1)
        with patch.object(overseas_feed,'now',return_value='2026-11-25T15:00:00+00:00'):
            cached = overseas_library.reference('',card['creation_reference_id'])
            self.assertEqual(cached['filming_basis'],saved['filming_basis'])

    def test_rotation_uses_original_id_for_older_issues_and_deduplicates_current_candidates(self):
        second_url = 'https://www.youtube.com/watch?v=98765432101'
        earlier = '2026-11-20T15:00:00+00:00'
        with D.db() as c, patch.object(overseas_visuals,'CASES',{}):
            other = {**self.item, 'url':second_url, 'id':'feed_second'}
            alias = {**self.item, 'url':self.url.replace('/watch?v=','/shorts/'), 'id':'feed_alias'}
            for item in (other,alias):
                c.execute('INSERT INTO overseas_feed_videos VALUES (?,?,?,?,?,?)',
                          (item['id'],item['url'],json.dumps(item),self.stamp,self.stamp,self.stamp))
            for url in (self.url,second_url):
                review.record(c,url,'keep',self.evidence,earlier)
            before = overseas_daily.select(c,self.stamp,False)['picks']
            self.assertEqual(len(before),2)
            first, second = [overseas_visuals.review_key(p['url']) for p in before]
            shown_url = 'https://youtu.be/'+first[1]
            for issue in (0,1):
                with self.subTest(issue=issue):
                    c.execute('DELETE FROM overseas_editions WHERE day=?',('2026-11-20',))
                    c.execute('INSERT INTO overseas_editions VALUES (?,?,?)',
                              ('2026-11-20',issue,json.dumps([{'url':shown_url}])))
                    after = overseas_daily.select(c,self.stamp,False)['picks']
                    self.assertEqual([overseas_visuals.review_key(p['url']) for p in after],[second,first])

    def test_two_editor_writes_preserve_one_first_match_and_valid_notes(self):
        def save(method):
            with D.db() as c:
                c.execute('BEGIN IMMEDIATE')
                review.record(c,self.url,'keep',{**self.evidence,'method':method},self.stamp)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(save,['固定机位翻纸盒','俯拍翻转纸盒']))
        with D.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM overseas_match_events').fetchone()[0],1)
            rows = c.execute('SELECT details FROM overseas_shot_reviews').fetchall()
            self.assertEqual(len(rows),1)
            self.assertIn(json.loads(rows[0][0])['method'], ('固定机位翻纸盒','俯拍翻转纸盒'))

    def test_rejected_candidate_excluded_and_history_keeps_missing_days_unknown(self):
        with D.db() as c:
            review.record(c,self.url,'keep',self.evidence,self.stamp)
            overseas_daily.select(c,self.stamp,True)
            next_day = '2026-11-25T15:00:00+00:00'
            review.record(c,self.url,'reject',{'reason':'场地无法复拍'},next_day)
            after = overseas_daily.select(c,next_day,True)
            self.assertNotIn(self.url,[p['url'] for p in after['picks']])
            stats = review.report(c,datetime.date(2026,11,25),3)
            self.assertIsNone(stats['days'][0]['front_count'])
            self.assertIsNone(stats['days'][1]['overlap_yesterday'])
            self.assertEqual(after['repeated_front'],stats['days'][2]['overlap_yesterday'])
            self.assertEqual(stats['shootable_rate'],0)
            self.assertEqual(stats['days'][0]['sync'],'unknown')
            self.assertIsNone(stats['days'][0]['first_matches_recorded'])
            c.execute("INSERT INTO overseas_sync_days VALUES ('2026-11-23',1),('2026-11-25',2)")
            updated = review.report(c,datetime.date(2026,11,25),3)
            self.assertIsNone(updated['days'][0]['first_matches_recorded'])
            self.assertEqual(updated['days'][2]['first_matches_recorded'],0)
            self.assertEqual(updated['days'][2]['sync'],'complete')


if __name__ == '__main__':
    unittest.main()
