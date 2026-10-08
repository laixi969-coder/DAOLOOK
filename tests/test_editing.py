"""Real HTTP edit/save/restore, ownership and concurrency regressions."""
import concurrent.futures
import json
import unittest
from tests import test_original as fixture
from tests.test_app import Client
from server import editing


class EditingTests(unittest.TestCase):
    tearDown = fixture.OriginalTests.tearDown
    post = fixture.OriginalTests.post
    run_task = fixture.OriginalTests.run_task
    ws = fixture.OriginalTests.ws

    def setUp(self):
        fixture.OriginalTests.setUp(self)
        status, task = self.post('/api/original', {'platform':'xhs', 'topic':'办公室咖啡', 'temporary':'挂耳咖啡每包12克，每盒10包，45元。'})
        self.assertEqual(status, 202)
        self.run_task(task)
        self.original = self.ws()['creations'][0]
        self.cid = self.original['id']
        self.path = '/api/creations/' + self.cid

    def edit(self, changes, version=0):
        return self.post(self.path+'/edit', {'revision':version, 'changes':changes})

    def history(self):
        return self.c.req(self.path+'/revisions?project_id='+self.p)

    def test_save_restore_export_and_credits(self):
        credits = self.c.req('/api/bootstrap')[1]['credits']
        self.assertEqual(self.history()[1][0]['revision'], 0)
        status, saved = self.edit({'title':'我的咖啡新标题', 'body':'每包12克，你在哪喝咖啡？', 'tags':['咖啡','办公'], 'cta':'你在哪喝咖啡？'})
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved['revision'], 1)
        fresh = next(c for c in self.ws()['creations'] if c['id'] == self.cid)
        self.assertEqual(fresh['data']['title'], '我的咖啡新标题')
        self.assertEqual(fresh['revision'], 1)
        self.assertNotEqual(fresh['data']['quality']['status'], 'checked')
        self.assertEqual(fresh['data']['evidence'], self.original['data']['evidence'])
        self.assertEqual(len(self.ws()['creations']), 8)
        _, export = self.c.req('/api/export?project_id='+self.p, raw=True)
        self.assertIn('我的咖啡新标题', export.decode())
        status, restored = self.post(self.path+'/restore', {'revision':1,'restore_revision':0})
        self.assertEqual(status, 200, restored)
        self.assertEqual(restored['data'], self.original['data'])
        self.assertEqual(restored['revision'], 2)
        self.assertEqual([r['revision'] for r in self.history()[1]], [2,1,0])
        self.assertEqual(self.c.req('/api/bootstrap')[1]['credits'], credits)

    def test_invalid_edits_cannot_mutate_metadata(self):
        for changes in ({'title':''}, {'body':[]}, {'title':'x'*301}, {'tags':['#']}, {'tags':[{}]}, {'demo':False}, {'quality':{'status':'checked'}}, {'goal':'sales'}, {'comments':{}}):
            self.assertEqual(self.edit(changes)[0], 400, changes)
        self.assertEqual(self.edit({'title':'修改'}, True)[0], 400)
        self.assertEqual(self.post(self.path+'/restore', {'revision':0,'restore_revision':None})[0],400)
        self.assertEqual(self.history()[1][0]['data'], self.original['data'])

    def test_wrong_project_user_and_soft_deleted_are_hidden(self):
        other = Client(self.c.base) if hasattr(self.c, 'base') else Client(f'http://127.0.0.1:{self.server.server_address[1]}')
        other.req('/api/auth/demo','POST',{})
        other_project = other.req('/api/bootstrap')[1]['projects'][0]['id']
        self.assertEqual(other.req(self.path+'/revisions?project_id='+other_project)[0],404)
        self.assertEqual(other.req(self.path+'/edit','POST',{'project_id':other_project,'revision':0,'changes':{'title':'偷改'}})[0],404)
        p2 = self.c.req('/api/projects','POST',{'name':'另一个项目'})[1]['id']
        self.assertEqual(self.c.req(self.path+'/revisions?project_id='+p2)[0],404)
        self.c.req(self.path,'DELETE',{'project_id':self.p})
        self.assertEqual(self.history()[0],404)
        self.assertEqual(self.edit({'title':'已删除'})[0],404)

    def test_concurrent_saves_and_stale_restores_do_not_overwrite(self):
        def save(title):
            try:
                return editing.save(self.cid,self.p,0,{'title':title})['revision']
            except editing.EditError as e:
                return e.status
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save,['第一份修改','第二份修改']))
        self.assertEqual(sorted(results),[1,409])
        self.assertEqual(self.edit({'body':'过期修改'})[0],409)
        self.assertEqual(self.post(self.path+'/restore',{'revision':0,'restore_revision':0})[0],409)
        self.assertEqual(len(self.history()[1]),2)

    def test_published_and_recorded_results_keep_original_copy(self):
        self.post('/api/tracking/'+self.cid,{'status':'published'})
        self.assertEqual(self.edit({'title':'不能替换发布原文'})[0],409)
        self.post('/api/tracking/'+self.cid,{'status':'draft'})
        self.assertEqual(self.edit({'title':'撤回后可编辑'})[0],200)
        self.post('/api/results/'+self.cid,{'results':{'views':0}})
        self.assertEqual(self.edit({'title':'不能误配历史结果'},1)[0],409)
        self.assertEqual(self.post(self.path+'/restore',{'revision':1,'restore_revision':0})[0],409)

    def test_manual_edit_rechecks_copy_without_certifying_facts(self):
        original = {'title':'原始标题','body':'原文','tags':[], 'cta':'', 'audience':'办公室','value':'规格', 'quality':{'status':'checked','issues':[]}, 'missing':['旧缺项'], 'titles':['过期备选XX'], 'evidence':[]}
        updated = editing.edited_data(original,{'body':'全新的事实','cta':'新的事实'},'xhs')
        self.assertEqual(updated['quality']['status'],'review')
        self.assertIn('原始引用不代表', updated['quality']['note'])
        updated = editing.edited_data(original,{'body':'售价XX，待填写'},'xhs')
        self.assertEqual(updated['quality']['status'],'needs_input')
        self.assertTrue(any('未填写' in s for s in updated['quality']['issues']))

    def test_noop_save_does_not_create_versions(self):
        status, result = self.edit({'title':self.original['data']['title']})
        self.assertEqual(status,200)
        self.assertEqual(result['revision'],0)
        self.assertEqual(len(self.history()[1]),1)

    def test_comments_are_restorable_and_metadata_is_retained(self):
        original_layout = self.original['data']['comment_layout']
        status, result = self.edit({'comments':{'pinned':'真实购买说明','knowledge':'产品规格\n第二条说明','atmosphere':'你通常在哪喝咖啡？'}})
        self.assertEqual(status,200,result)
        self.assertEqual(result['data']['comment_layout']['pinned']['text'],'真实购买说明')
        self.assertEqual(result['data']['comment_layout']['knowledge'],['产品规格','第二条说明'])
        self.assertEqual(result['data']['comment_layout']['first_hour'],original_layout['first_hour'])
