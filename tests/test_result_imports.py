"""Project-scoped batch import, publication identity, and downstream learning."""
import csv
import io
import json
import unittest

from server import jobs, questions, result_imports
from tests import test_production as fixtures


class ResultImportTests(unittest.TestCase):
    setUp = fixtures.TrackingApiTests.setUp
    tearDown = fixtures.TrackingApiTests.tearDown
    ws = fixtures.TrackingApiTests.ws
    post = fixtures.TrackingApiTests.post
    formal = fixtures.TrackingApiTests.formal

    def account(self, name):
        return self.post('/api/assets', {'kind':'账号','name':name,'content':'测试账号'})[1]['id']

    def bind(self, cid, account, post, traffic='organic'):
        return self.post('/api/tracking/'+cid, {'status':'published','published_at':'2020-04-01T12:00:00+00:00',
                        'account_id':account,'post_id':post,'traffic_type':traffic})

    def csv(self, account, entries):
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(result_imports.COLUMNS.values())
        for post, period, values in entries:
            writer.writerow(['xhs', account, post, 0, period, *[values.get(k,'') for k in ('views','leads','orders','spend')]])
        return stream.getvalue()

    def effect(self, cid):
        return next(x['results'] for x in self.ws()['creations'] if x['id']==cid)

    def test_template_preview_unaudited_rows_conflict_then_merge_idempotently(self):
        acc = self.account('试点主号')
        cid, other = self.ids[:2]
        self.formal([cid,other])
        self.assertEqual(self.bind(cid,acc,'000012')[0],200)
        self.assertEqual(self.bind(other,acc,'000012')[0],400)
        self.assertEqual(self.post('/api/results/'+cid,{'results':{'leads':4,'views':3,'note':'手工备注'}})[0],200)
        self.assertEqual(self.post('/api/results/'+cid,{'window':'7d','results':{'orders':2,'note':'手工备注'}})[0],200)
        raw = self.c.req(f'/api/results/template?project_id={self.p}&platform=xhs&account_id={acc}',raw=True)[1]
        self.assertIn('000012',raw.decode('utf-8-sig'))
        request = {'account_id':acc,'platform':'xhs','csv': self.csv(acc,[
            ('000012','截至目前',{'views':100}),('000012','7天',{'views':90,'leads':0})])}
        status, preview = self.post('/api/results/preview',request)
        self.assertEqual(status,200,preview)
        self.assertTrue(preview['valid'])
        self.assertEqual(preview['rows'][0]['changes']['views'], {'old':3,'new':100})
        self.assertEqual(self.effect(cid)['views'],3)
        # Unreviewed changes made after preview must never be overwritten.
        self.post('/api/results/'+cid,{'results':{'views':5,'leads':4,'note':'更新备注'}})
        self.assertEqual(self.post('/api/results/import',{**request,'token':preview['token']})[0],409)
        preview = self.post('/api/results/preview',request)[1]
        self.assertEqual(self.post('/api/results/import',{**request,'token':preview['token']})[0],200)
        after = self.effect(cid)
        self.assertEqual((after['views'],after['leads'],after['note']), (100,4,'更新备注'))
        self.assertNotIn('orders',after)
        self.assertEqual((after['windows']['7d']['views'],after['windows']['7d']['leads'],after['windows']['7d']['orders']), (90,0,2))
        self.assertEqual(self.post('/api/results/import',{**request,'token':preview['token']})[0],200)
        again = self.post('/api/results/preview',request)[1]
        self.assertEqual([row['state'] for row in again['rows']], ['unchanged','unchanged'])
        self.assertEqual(self.post('/api/results/import',{**request,'token':again['token']})[0],200)
        self.assertEqual(self.effect(cid),after)  # includes recorded_at stamps

    def test_spreadsheet_template_protects_long_numeric_and_formula_like_ids(self):
        acc = '00000000000000000000000000000012'
        with fixtures.D.db() as c:
            c.execute("INSERT INTO assets(id,project_id,name,kind,content,created_at) VALUES(?,?,?,?,?,?)",
                      (acc,self.p,'纯数字账号','账号','测试账号',fixtures.D.now()))
        posts = ['0000001234567890123456789','-12345']
        for cid, post in zip(self.ids,posts):
            self.assertEqual(self.bind(cid,acc,post)[0],200)
        raw = self.c.req(f'/api/results/template?project_id={self.p}&platform=xhs&account_id={acc}',raw=True)[1]
        rows = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        self.assertEqual({row[1] for row in rows[1:]},{'id:'+acc})
        self.assertEqual({row[2] for row in rows[1:]},{'id:'+post for post in posts})
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(rows[0])
        for row in rows[1:]:
            row[5]='0'
            writer.writerow(row)
        request={'csv':out.getvalue(),'account_id':acc,'platform':'xhs'}
        preview = self.post('/api/results/preview',request)[1]
        self.assertTrue(preview['valid'],preview)
        self.assertEqual({r['post_id'] for r in preview['rows']},set(posts))
        self.assertEqual(self.post('/api/results/import',{**request,'token':preview['token']})[0],200)
        self.assertEqual([self.effect(cid)['views'] for cid in self.ids[:2]],[0,0])

    def test_spend_agrees_with_traffic_on_manual_import_and_reclassification(self):
        acc = self.account('主号')
        cid = self.ids[0]
        self.assertEqual(self.bind(cid,acc,'post')[0],200)
        for window in ('lifetime','7d'):
            self.assertEqual(self.post('/api/results/'+cid,{'window':window,'results':{'spend':1}})[0],400)
        request = {'csv':self.csv(acc,[('post','7d',{'spend':1})]),'platform':'xhs','account_id':acc}
        self.assertFalse(self.post('/api/results/preview',request)[1]['valid'])
        self.assertEqual(self.effect(cid),{})
        tracking = '/api/tracking/'+cid
        self.assertEqual(self.post(tracking,{'traffic_type':'paid'})[0],200)
        self.assertEqual(self.post('/api/results/'+cid,{'window':'7d','results':{'spend':1}})[0],200)
        self.assertEqual(self.post(tracking,{'traffic_type':'organic'})[0],400)
        self.assertEqual(self.post('/api/results/'+cid,{'window':'7d','results':{'spend':0}})[0],200)
        self.assertEqual(self.post(tracking,{'traffic_type':'organic'})[0],200)

    def test_legacy_results_cannot_be_attributed_to_another_account(self):
        original, other = self.account('旧主号'), self.account('新主号')
        cid = self.ids[0]
        tracking = '/api/tracking/'+cid
        self.assertEqual(self.post(tracking,{'status':'published','account_id':original})[0],200)
        self.assertEqual(self.post('/api/results/'+cid,{'results':{'leads':0}})[0],200)
        for fields in ({'account_id':other}, {'status':'draft','account_id':None},
                       {'account_id':other,'post_id':'misassigned'}):
            self.assertEqual(self.post(tracking,fields)[0],400)
        self.assertEqual(self.bind(cid,original,'old')[0],200)
        withdrawn = self.post(tracking,{'status':'draft'})[1]
        self.assertEqual((withdrawn['post_id'],withdrawn['traffic_type']),('old','organic'))
        self.assertEqual(self.bind(cid,original,withdrawn['post_id'],withdrawn['traffic_type'])[0],200)

    def test_errors_are_atomic_and_bound_to_account_work_revision_period(self):
        account, secondary = self.account('主号'), self.account('分号')
        cid, other = self.ids[:2]
        self.bind(cid,account,'post1')
        self.bind(other,secondary,'post2')
        for entries, fragment in [
            ([('post1','7天',{'views':9}),('post2','7d',{'views':12})], '找不到'),
            ([('post1','7天',{'views':9}),('post1','7d',{'views':12})], '重复'),
            ([('post1','7d',{'views':-2})], '非负'),
        ]:
            with self.subTest(fragment=fragment):
                request={'csv':self.csv(account,entries),'account_id':account,'platform':'xhs'}
                plan=self.post('/api/results/preview',request)[1]
                self.assertFalse(plan['valid'])
                self.assertTrue(any(fragment in r.get('message','') for r in plan['rows']))
                self.assertEqual(self.post('/api/results/import',{**request,'token':plan['token']})[0],409)
                self.assertEqual(self.effect(cid),{})
        request={'csv':self.csv(account,[('post1','7d',{'views':10})]),'account_id':account,'platform':'xhs'}
        self.assertFalse(self.post('/api/results/preview',{**request,'csv':request['csv'].replace(',0,7d',',2,7d')})[1]['valid'])
        self.assertFalse(self.post('/api/results/preview',{**request,'account_id':secondary})[1]['valid'])
        other_project=self.c.req('/api/projects','POST',{'name':'其他项目'})[1]['id']
        self.assertEqual(self.post('/api/results/preview',{**request,'project_id':other_project})[0],400)
        self.post('/api/tracking/'+cid,{'published_at':'2099-01-01T00:00:00Z'})
        self.assertIn('观察期',self.post('/api/results/preview',request)[1]['rows'][0]['message'])
        self.post('/api/tracking/'+cid,{'status':'draft'})
        self.assertFalse(self.post('/api/results/preview',request)[1]['valid'])

    def test_selected_account_filters_goal_metric_before_twelve_work_limit(self):
        acc = self.account('只看有效咨询')
        first, second = self.ids[:2]
        self.formal([first,second])
        self.bind(first,acc,'window0')
        self.bind(second,acc,'total0')
        self.post('/api/results/'+first,{'window':'7d','results':{'leads':0}})
        self.post('/api/results/'+second,{'results':{'leads':0}})
        with fixtures.D.db() as c:
            for n in range(14):
                cid = fixtures.D.uid()
                c.execute("""INSERT INTO creation_outputs(id,project_id,source_id,task_id,data,created_at)
                    SELECT ?,project_id,source_id,task_id,data,created_at FROM creation_outputs WHERE id=?""",(cid,first))
                c.execute("""INSERT INTO creation_tracking(creation_id,project_id,status,account_id,published_at)
                    VALUES(?,?,'published',?,'2020-04-01T12:00:00+00:00')""",(cid,self.p,acc))
                result = [{'note':'仅备注'},{'views':42},{'windows':{'7d':{'published_at':'上次发布','leads':10}}}][n % 3]
                c.execute("INSERT INTO creation_results VALUES(?,?,?,?)",(cid,self.p,fixtures.D.dumps(result),f'2099-06-{n+1:02d}'))
        scoped = jobs.history_results(self.p,'xhs','leads',acc)
        self.assertEqual(len(scoped),2)
        self.assertTrue(any(r['results'].get('leads')==0 for r in scoped))
        self.assertTrue(any(r['results'].get('windows',{}).get('7d',{}).get('leads')==0 for r in scoped))
        counts=self.ws()['feedback_accounts']['groups']
        self.assertEqual(sum(r['posts'] for r in counts if r['account_id']==acc),len(scoped))
        self.assertEqual(len(jobs.history_results(self.p,'xhs','leads')),12)

    def test_feedback_selects_the_requested_account_and_keeps_traffic_groups(self):
        a, b = self.account('A'), self.account('B')
        self.formal(self.ids[:3])
        for i,(acc,traffic) in enumerate([(a,'organic'),(a,'paid'),(b,'unknown')]):
            self.bind(self.ids[i],acc,'same' if i!=1 else 'other',traffic)
            self.post('/api/results/'+self.ids[i],{'results':{'leads':i,'note':f'样本{i}'}})
        history = jobs.history_results(self.p,'xhs','leads',a)
        self.assertEqual({r['traffic_type'] for r in history},{'organic','paid'})
        self.assertEqual({r['account_id'] for r in history},{a})
        with fixtures.D.db() as c:
            notes = questions.context(c,self.p,'xhs','样本',account_id=a)
        self.assertNotIn('样本2',json.dumps(notes,ensure_ascii=False))
        counts = self.ws()['feedback_accounts']['groups']
        self.assertEqual(sorted((g['traffic_type'],g['posts']) for g in counts if g['account_id']==a), [('organic',1),('paid',1)])
        invalid=self.post('/api/original',{'platform':'xhs','topic':'咖啡','temporary':'介绍产品','feedback_account_id':'missing'})
        self.assertEqual(invalid[0],400)
        status,req=self.post('/api/original',{'platform':'xhs','topic':'咖啡','temporary':'介绍产品','feedback_account_id':a,'skip_question':True})
        self.assertEqual(status,202)
        with fixtures.D.db() as c:
            payload=json.loads(c.execute('SELECT payload FROM tasks WHERE id=?',(req['task_ids'][0],)).fetchone()[0])
        self.assertEqual(payload['brief']['feedback_account_id'],a)


if __name__ == '__main__':
    unittest.main()
