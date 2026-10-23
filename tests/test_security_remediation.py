"""Regression checks for the ten audited risks; isolated DBs, no real paid calls."""
import base64
from concurrent.futures import ThreadPoolExecutor
import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock
from http.server import ThreadingHTTPServer
from server import app, jobs, adapters, spending, resource_limits, workspace, secret_store, access, mailer
from server.config import load_env
from tests.test_app import Client

D=importlib.import_module('server.db')
ROOT=Path(__file__).resolve().parent.parent


class RemediationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path_patch=patch.object(D,'DB_PATH',str(Path(self.temp.name)/'data/db.sqlite'))
        self.path_patch.start();D.init();app.RATE.clear()
        self.queue=patch.object(jobs.Q,'put');self.queue.start()
        self.admin_id=app.new_user('admin@audit.test','initial-password-123','admin')
        self.user=app.new_user('reader+one@audit.test','user-password-123')
        with D.db() as c:self.project=c.execute('SELECT id FROM projects WHERE user_id=?',(self.user,)).fetchone()[0]
        self.server=ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.client=Client('http://127.0.0.1:'+str(self.server.server_address[1]))
        self.admin=Client(self.client.base)
        self.assertEqual(self.client.req('/api/auth/login','POST',{'email':'reader+one@audit.test','password':'user-password-123'})[0],200)
        self.assertEqual(self.admin.req('/api/auth/login','POST',{'email':'admin@audit.test','password':'initial-password-123'})[0],200)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.queue.stop();self.path_patch.stop();self.temp.cleanup()

    def setting(self,key,value):
        with D.db() as c:c.execute('UPDATE settings SET value=? WHERE key=?',(D.dumps(value),key))

    def post(self,path,data):return self.client.req(path,'POST',{'project_id':self.project,**data})

    def live(self):
        with D.db() as c:
            c.execute('BEGIN IMMEDIATE')
            access.approve(c,self.user,self.admin_id,'test_admin',preserve_balance=True)
        self.setting('mode','live')
        cfg=D.setting('tikhub');cfg['api_key']='mock-only-key';self.setting('tikhub',cfg)

    def test_admin_bootstrap_preserves_changed_password_and_reset_revokes_sessions(self):
        self.assertEqual(self.admin.req('/api/admin/password','POST',{'user_id':self.admin_id,'password':'replacement-password-123'})[0],200)
        self.assertEqual(self.admin.req('/api/bootstrap')[0],401)
        with patch.dict(os.environ,{'DAOLOOK_ADMIN_EMAIL':'admin@audit.test','DAOLOOK_ADMIN_PASSWORD':'initial-password-123'}):app.bootstrap_admin()
        self.assertEqual(self.admin.req('/api/auth/login','POST',{'email':'admin@audit.test','password':'initial-password-123'})[0],401)
        self.assertEqual(self.admin.req('/api/auth/login','POST',{'email':'admin@audit.test','password':'replacement-password-123'})[0],200)
        with patch.dict(os.environ,{'DAOLOOK_ADMIN_EMAIL':'reader+one@audit.test','DAOLOOK_ADMIN_PASSWORD':'initial-password-123'}):
            with self.assertRaises(RuntimeError):app.bootstrap_admin()

    @unittest.skipIf(os.name=='nt','POSIX permissions')
    def test_private_files_and_sidecar_secret_survive_restart(self):
        env=Path(self.temp.name)/'.env';env.write_text('AUDIT_TEST_FLAG=ok');env.chmod(0o644)
        with patch.dict(os.environ,{},clear=False):load_env(env)
        self.assertEqual(env.stat().st_mode&0o777,0o600)
        self.assertEqual(Path(D.DB_PATH).stat().st_mode&0o777,0o600)
        self.assertEqual(Path(D.DB_PATH).parent.stat().st_mode&0o777,0o700)
        cfg=D.setting('provider');cfg['api_key']='private-provider-secret-unique'
        self.assertEqual(self.admin.req('/api/admin/config','POST',{'provider':cfg})[0],200)
        with D.db() as c:stored=json.loads(c.execute("SELECT value FROM settings WHERE key='provider'").fetchone()[0])
        self.assertTrue(stored['api_key'].startswith(secret_store.PREFIX))
        self.assertNotIn(cfg['api_key'],json.dumps(stored))
        D.init();self.assertEqual(D.setting('provider')['api_key'],cfg['api_key'])
        for file in secret_store.directory().iterdir():self.assertEqual(file.stat().st_mode&0o777,0o600)

    def test_live_cancel_only_before_worker_claim(self):
        self.live()
        payload={'source_id':D.uid(),'brief':{'platform':'xhs','topic':'咖啡','goal':'leads'},'temporary':'真实资料'}
        queued=jobs.submit(self.user,self.project,'original',payload)
        jobs.cancel(queued,self.user)
        started=jobs.submit(self.user,self.project,'original',payload)
        entered,release=threading.Event(),threading.Event()
        def response(*a,**k):
            entered.set();release.wait(3);return adapters.demo_outputs('xhs','咖啡',1),'mock/model'
        with patch.object(adapters,'fetch_benchmark',return_value={}),patch.object(adapters,'create_original',side_effect=response):
            thread=threading.Thread(target=jobs.run,args=(started,));thread.start();self.assertTrue(entered.wait(2))
            try:
                with self.assertRaises(jobs.TaskAdmissionError):jobs.cancel(started,self.user)
            finally:release.set();thread.join(3)
        with D.db() as c:
            self.assertEqual(c.execute('SELECT state FROM tasks WHERE id=?',(started,)).fetchone()[0],'SUCCEEDED')
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts WHERE user_id=?',(self.user,)).fetchone()),(85,0))

    def test_search_rejects_zero_balance_then_queues_and_refunds_cached_search(self):
        self.live()
        with D.db() as c:c.execute('UPDATE credit_accounts SET balance=0 WHERE user_id=?',(self.user,))
        with patch.object(adapters.TikHubAdapter,'call') as call:
            self.assertEqual(self.post('/api/overseas/search',{'platform':'tiktok','query':'charger'})[0],400)
            call.assert_not_called()
        with D.db() as c:c.execute('UPDATE credit_accounts SET balance=5 WHERE user_id=?',(self.user,))
        raw={'items':[{'id':'1234567890123456789','desc':'charger','author':{'uniqueId':'test'}}]}
        with patch.object(adapters.TikHubAdapter,'call',return_value=raw) as call:
            for _ in range(2):
                status,result=self.post('/api/overseas/search',{'platform':'tiktok','query':'charger'})
                self.assertEqual(status,202,result);jobs.run(result['task_ids'][0])
            self.assertEqual(call.call_count,1)
        with D.db() as c:self.assertEqual(c.execute('SELECT balance FROM credit_accounts WHERE user_id=?',(self.user,)).fetchone()[0],4)

    def test_live_registration_requires_mailbox_and_verified_grants_have_total_cap(self):
        self.live()
        self.assertEqual(self.client.req('/api/auth/register','POST',{'email':'new+alias@audit.test','password':'new-password-123'})[0],403)
        self.setting('signup',{'whitelist':True,'emails':['a@audit.test','b@audit.test'],'welcome_credits':100})
        self.assertEqual(self.client.req('/api/auth/register','POST',{'email':'a@audit.test','password':'new-password-123'})[0],403)
        with patch.dict(os.environ,{'DAOLOOK_SIGNUP_DAILY_CREDITS':'100','DAOLOOK_SIGNUP_TOTAL_CREDITS':'100'}),patch.object(mailer,'enabled',return_value=True),patch.object(mailer,'verify'):
            balances=[]
            for email in ('a@audit.test','b@audit.test'):
                client=Client(self.client.base)
                self.assertEqual(client.req('/api/auth/register','POST',{'email':email,'password':'new-password-123'})[0],200)
                balances.append(client.req('/api/bootstrap')[1]['credits']['balance'])
        self.assertEqual(balances,[100,0])

    def test_backup_missing_source_fails_without_rotation_and_restore_roundtrip(self):
        folder=Path(self.temp.name)/'backups';folder.mkdir(mode=0o700);previous=folder/'daolook-old.db';previous.write_text('do not rotate')
        missing=Path(self.temp.name)/'missing.db'
        result=subprocess.run([sys.executable,'scripts/backup_db.py','--db',str(missing),'--dir',str(folder),'--keep','1'],cwd=ROOT,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertFalse(missing.exists());self.assertTrue(previous.exists())
        from scripts.backup_db import snapshot
        backup=snapshot(D.DB_PATH,folder/'snapshot.db')
        restored=snapshot(backup,Path(self.temp.name)/'restored/db.sqlite')
        with sqlite3.connect(restored) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],2)
        with self.assertRaises(ValueError):snapshot(backup,restored)

    def test_failure_refund_retries_without_reissuing_job(self):
        with patch.object(jobs,'fail',side_effect=[sqlite3.OperationalError('locked'),None]) as fail,patch('threading.Event.wait'):
            jobs.settle_failure('test-task','upstream failed')
        self.assertEqual(fail.call_count,2);self.assertEqual(jobs.worker_health()['settlement_errors'],0)
        dead=MagicMock();dead.is_alive.return_value=False
        with patch.object(jobs,'WORKERS',[dead]):self.assertEqual(self.client.req('/api/health')[0],503)

    def test_concurrent_budget_reservations_are_atomic_and_fail_closed(self):
        self.live()
        env={'DAOLOOK_EXTERNAL_PRICES':json.dumps({'tikhub':{'per_call':10}}),'DAOLOOK_USER_DAILY_BUDGET_MICROUSD':'15','DAOLOOK_DAILY_BUDGET_MICROUSD':'100'}
        def reserve(_):
            with spending.scope(self.user):
                try:return spending.reserve('tikhub',None)
                except spending.BudgetExceeded:return None
        with patch.dict(os.environ,env),ThreadPoolExecutor(max_workers=5) as pool:
            ids=[ident for ident in pool.map(reserve,range(5)) if ident]
        self.assertEqual(len(ids),1)
        spending.finish(ids[0],failed=True)
        with patch.dict(os.environ,env),spending.scope(self.user):
            with self.assertRaises(spending.BudgetExceeded):spending.reserve('tikhub',None)
            with self.assertRaises(spending.BudgetExceeded):spending.reserve('model:unknown',{})
        with D.db() as c:self.assertEqual(c.execute('SELECT SUM(reserved) FROM external_calls').fetchone()[0],10)

    def test_repeated_worker_start_never_refunds_active_work(self):
        ident=jobs.submit(self.user,self.project,'original',{'source_id':D.uid(),'brief':{'platform':'xhs','topic':'咖啡','goal':'leads'},'temporary':'事实'})
        alive=MagicMock();alive.is_alive.return_value=True
        with patch.object(jobs,'WORKERS',[alive]),self.assertRaises(RuntimeError):jobs.start()
        with D.db() as c:
            self.assertEqual(c.execute('SELECT state FROM tasks WHERE id=?',(ident,)).fetchone()[0],'PENDING')
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts WHERE user_id=?',(self.user,)).fetchone()),(85,15))

    def test_long_asset_list_is_preview_only_and_detail_preserves_original(self):
        content='原文'*600
        status,item=self.post('/api/assets',{'name':'长资料','kind':'产品信息','content':content})
        self.assertEqual(status,200)
        listed=workspace.page(self.project)['assets'][0]
        self.assertEqual(len(listed['content']),1000);self.assertTrue(listed['content_truncated'])
        self.assertEqual(self.client.req('/api/assets/'+item['id']+'?project_id='+self.project)[1]['content'],content)

    def test_model_request_output_bound_and_usage_capture(self):
        choices={'choices':[{'message':{'content':'{}'}}],'usage':{'prompt_tokens':3,'completion_tokens':4}}
        options=[('test',{'base_url':'https://model.example','api_key':'mock'},'model')]
        with patch.object(adapters,'candidates',return_value=options),patch.object(adapters,'request_json',return_value=choices) as request:
            adapters.model_json({}, {}, 'prompt')
        self.assertEqual(request.call_args.args[2]['max_tokens'],resource_limits.MAX_OUTPUT_TOKENS)
        self.live()
        env={'DAOLOOK_EXTERNAL_PRICES':json.dumps({'tikhub':{'per_call':10}})}
        with patch.dict(os.environ,env),spending.scope(self.user):
            ident=spending.reserve('tikhub',None);spending.finish(ident,choices)
        with D.db() as c:self.assertEqual(tuple(c.execute('SELECT input_tokens,output_tokens FROM external_calls WHERE id=?',(ident,)).fetchone()),(3,4))

    def test_workspace_keyset_no_duplicates_and_private_lazy_media(self):
        with D.db() as c:
            for n in range(61):
                c.execute('INSERT INTO assets VALUES (?,?,?,?,?,?)',(D.uid(),self.project,'资料'+str(n),'产品信息','内容','2026-01-01T00:00:00+00:00'))
            photo='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\ncontent').decode()
            ident=D.uid();c.execute('INSERT INTO assets VALUES (?,?,?,?,?,?)',(ident,self.project,'图','图片',photo,D.now()))
        cursor='';ids=[]
        while True:
            value=workspace.page(self.project,cursor,10);ids.extend(a['id'] for a in value['assets'])
            if not value['pagination']['more']:break
            cursor=value['pagination']['cursor']
        self.assertEqual(len(ids),62);self.assertEqual(len(set(ids)),62)
        value=workspace.page(self.project)
        image=next(a for a in value['assets'] if a['kind']=='图片')
        self.assertNotIn('base64',image['content'])
        status,blob=self.client.req(image['content'],raw=True);self.assertEqual(status,200);self.assertTrue(blob.startswith(b'\x89PNG'))
        other=app.new_user('other@audit.test','other-password-123')
        with D.db() as c:other_project=c.execute('SELECT id FROM projects WHERE user_id=?',(other,)).fetchone()[0]
        self.assertEqual(self.client.req('/api/media/assets/'+ident+'?project_id='+other_project,raw=True)[0],404)
        self.assertEqual(self.client.req('/api/assets/'+ident+'?project_id='+self.project)[1]['content'],photo)

    def test_live_task_budget_survives_switch_to_demo(self):
        self.live()
        payload={'source_id':D.uid(),'brief':{'platform':'xhs','topic':'咖啡','goal':'leads'},'temporary':'事实'}
        ident=jobs.submit(self.user,self.project,'original',payload)
        self.setting('mode','demo')
        with patch.dict(os.environ,{'DAOLOOK_EXTERNAL_PRICES':'{}'}),patch.object(adapters,'fetch_benchmark',return_value={}),patch.object(adapters,'create_original',side_effect=lambda *a,**k:spending.reserve('tikhub',None)):
            with self.assertRaises(spending.BudgetExceeded):jobs.run(ident)

    def test_revisions_also_enforce_storage_quota(self):
        from server import editing
        ident=jobs.submit(self.user,self.project,'original',{'source_id':D.uid(),'brief':{'platform':'xhs','topic':'咖啡','goal':'leads'},'temporary':'事实'})
        jobs.run(ident)
        with D.db() as c:
            creation=c.execute('SELECT id FROM creation_outputs WHERE project_id=?',(self.project,)).fetchone()[0]
            before=c.execute('SELECT count(*) FROM creation_revisions').fetchone()[0]
        with patch.dict(os.environ,{'DAOLOOK_USER_STORAGE_BYTES':'1'}):
            with self.assertRaises(ValueError):editing.save(creation,self.project,0,{'title':'更新的标题'})
        with D.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM creation_revisions').fetchone()[0],before)

    def test_asset_length_selection_and_storage_quota_are_server_side(self):
        self.assertEqual(self.post('/api/assets',{'name':'large','kind':'产品信息','content':'x'*100001})[0],400)
        with patch.dict(os.environ,{'DAOLOOK_USER_STORAGE_BYTES':'100'}):
            self.assertEqual(self.post('/api/assets',{'name':'large','kind':'产品信息','content':'x'*101})[0],400)
        with self.assertRaises(ValueError):resource_limits.validate_inputs({'assets':['x']*13})
        with self.assertRaises(ValueError):resource_limits.validate_inputs({'temporary':'中'*50000})

    def test_admin_audit_has_actor_and_no_secrets(self):
        secret='should-not-be-logged-password'
        self.assertEqual(self.admin.req('/api/admin/password','POST',{'user_id':self.user,'password':secret})[0],200)
        self.assertEqual(self.admin.req('/api/admin/grant','POST',{'user_id':self.user,'amount':7})[0],200)
        rows=self.admin.req('/api/admin/audit')[1]
        self.assertEqual({r['action'] for r in rows},{'user.password_reset','credits.adjust'})
        self.assertTrue(all(r['actor_id']==self.admin_id and r['request_id'] for r in rows))
        self.assertNotIn(secret,json.dumps(rows))
        anonymous=Client(self.client.base);self.assertEqual(anonymous.req('/api/admin/audit')[0],401)

    def test_registration_mode_race_does_not_invent_mailbox_proof(self):
        calls=[]
        def changed_configuration():
            calls.append(True)
            self.setting('mode','live')
            return len(calls)>1
        fresh=Client(self.client.base)
        with patch.object(mailer,'enabled',side_effect=changed_configuration),patch.object(mailer,'verify') as verify:
            status,result=fresh.req('/api/auth/register','POST',{'email':'race@audit.test','password':'test-password-123'})
            self.assertEqual(status,200,result)
            verify.assert_not_called()
        boot=fresh.req('/api/bootstrap')[1]
        self.assertFalse(boot['user']['live_access'])
        with self.assertRaisesRegex(ValueError,'验证'):
            jobs.submit(boot['user']['id'],boot['projects'][0]['id'],'search',{'platform':'tiktok','query':'coffee'})

    def test_demo_seed_cannot_bypass_total_storage_limit(self):
        with D.db() as c:before=c.execute('SELECT count(*) FROM users').fetchone()[0]
        with patch.dict(os.environ,{'DAOLOOK_TOTAL_STORAGE_BYTES':'1'}):
            with self.assertRaisesRegex(ValueError,'存储'):
                app.new_user('demo-seed@daolook.local',demo=True)
        with D.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM users').fetchone()[0],before)
            self.assertEqual(c.execute('SELECT count(*) FROM source_contents').fetchone()[0],0)

    def test_worker_waits_for_admission_commit_before_reading_identity(self):
        entered=threading.Event();finished=threading.Event();threads=[];early=[];errors=[]
        def dispatch(ident,**kwargs):
            def consume():
                entered.set()
                try:jobs.run(ident)
                except Exception as error:errors.append(error)
                finally:finished.set()
            thread=threading.Thread(target=consume);threads.append(thread);thread.start()
            self.assertTrue(entered.wait(1))
            # Admission still owns BEGIN IMMEDIATE here. An ordinary read sees
            # no task yet; the worker must wait instead of discarding this ID.
            early.append(finished.wait(.1))
        with patch.object(jobs.Q,'put',side_effect=dispatch):
            ident=jobs.submit(self.user,self.project,'original',{'source_id':D.uid(),'brief':{'platform':'xhs','topic':'咖啡','goal':'leads'},'temporary':'产品事实'})
        threads[0].join(3)
        self.assertFalse(threads[0].is_alive());self.assertFalse(early[0]);self.assertEqual(errors,[])
        with D.db() as c:
            self.assertEqual(c.execute('SELECT state FROM tasks WHERE id=?',(ident,)).fetchone()[0],'SUCCEEDED')
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts WHERE user_id=?',(self.user,)).fetchone()),(85,0))

    def test_demo_and_legacy_accounts_cannot_spend_after_mode_switch(self):
        demo=app.new_user('demo-review@daolook.local',demo=True)
        with D.db() as c:
            project=c.execute('SELECT id FROM projects WHERE user_id=?',(demo,)).fetchone()[0]
        self.setting('mode','live')
        for user,project_id in ((demo,project),(self.user,self.project)):
            with self.assertRaisesRegex(ValueError,'演示|验证'):
                jobs.submit(user,project_id,'analyze',{'text':'咖啡','entry':'keyword'})
        with D.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0],0)
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts WHERE user_id=?',(demo,)).fetchone()),(300,0))
        self.assertEqual(self.admin.req('/api/admin/access','POST',{'user_id':demo,'preserve_balance':True})[0],400)

    def test_mailbox_activation_requires_own_code_and_clears_legacy_promotion(self):
        from tests.test_mail import MAIL
        self.setting('mail',MAIL)
        self.setting('mode','live')
        sent=[]
        self.assertEqual(self.client.req('/api/auth/verify','POST',{'code':'123456'})[0],400)
        self.assertEqual(self.client.req('/api/auth/code','POST',{'email':'admin@audit.test','purpose':'verify'})[0],403)
        with patch.object(mailer,'send_mail',side_effect=lambda to,subject,text:sent.append(text)):
            self.assertEqual(self.client.req('/api/auth/code','POST',{'email':'reader+one@audit.test','purpose':'verify'})[0],200)
        code=sent[0].split('验证码是 ')[1][:6]
        self.assertEqual(self.client.req('/api/auth/verify','POST',{'code':code})[0],200)
        boot=self.client.req('/api/bootstrap')[1]
        self.assertTrue(boot['user']['live_access']);self.assertEqual(boot['credits']['balance'],0)
        self.assertEqual(self.client.req('/api/auth/verify','POST',{'code':code})[0],400)
        with D.db() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM audit_events WHERE action='account.live_approved'").fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM signup_grants').fetchone()[0],0)

    def test_search_quota_failure_rolls_back_every_result_and_cache(self):
        self.live()
        queued=jobs.submit(self.user,self.project,'search',{'platform':'tiktok','query':'charger'})
        raw={'items':[{'id':str(1234567890123456789+i),'desc':'x'*2000,'author':{'uniqueId':'brand'}} for i in range(2)]}
        with D.db() as c:limit=resource_limits.usage(c,self.user)+3000
        with patch.dict(os.environ,{'DAOLOOK_USER_STORAGE_BYTES':str(limit)}),patch.object(adapters.TikHubAdapter,'call',return_value=raw) as call:
            with self.assertRaisesRegex(ValueError,'存储'):
                jobs.run(queued)
        self.assertEqual(call.call_count,1)
        jobs.fail(queued,'存储额度已满')
        with D.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM overseas_ideas').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM overseas_searches').fetchone()[0],0)
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts WHERE user_id=?',(self.user,)).fetchone()),(100,0))

    def test_original_quota_counts_saved_benchmark_before_commit(self):
        self.live()
        queued=jobs.submit(self.user,self.project,'original',{'source_id':D.uid(),'brief':{'platform':'xhs','topic':'咖啡','goal':'leads'},'temporary':'产品事实'})
        with D.db() as c:limit=resource_limits.usage(c,self.user)+15000
        with patch.dict(os.environ,{'DAOLOOK_USER_STORAGE_BYTES':str(limit)}),patch.object(adapters,'fetch_benchmark',return_value={'note':'x'*30000}),patch.object(adapters,'create_original',return_value=(adapters.demo_outputs('xhs','咖啡',1),'mock')):
            with self.assertRaisesRegex(ValueError,'存储'):jobs.run(queued)
        jobs.fail(queued,'存储额度已满')
        with D.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM source_contents WHERE project_id=?',(self.project,)).fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM creation_outputs WHERE project_id=?',(self.project,)).fetchone()[0],0)
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts WHERE user_id=?',(self.user,)).fetchone()),(100,0))

    def test_quota_includes_analysis_and_result_writes_roll_back(self):
        queued=jobs.submit(self.user,self.project,'original',{'source_id':D.uid(),'brief':{'platform':'xhs','topic':'咖啡','goal':'leads'},'temporary':'产品事实'})
        jobs.run(queued)
        with D.db() as c:
            creation=c.execute('SELECT id,source_id FROM creation_outputs WHERE project_id=?',(self.project,)).fetchone()
            before=resource_limits.usage(c,self.user)
            blob=D.dumps({'analysis':'完整分析'*1000})
            c.execute('INSERT INTO analysis_outputs VALUES (?,?,?,?,?,?)',(D.uid(),creation['source_id'],blob,None,None,D.now()))
            self.assertEqual(resource_limits.usage(c,self.user)-before,len(blob.encode()))
            limit=resource_limits.usage(c,self.user)
        with patch.dict(os.environ,{'DAOLOOK_USER_STORAGE_BYTES':str(limit)}):
            self.assertEqual(self.post('/api/results/'+creation['id'],{'results':{'views':10}})[0],400)
            self.assertEqual(self.post('/api/tracking/'+creation['id'],{'status':'published','checklist':{}})[0],400)
        with D.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM creation_results').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM creation_tracking').fetchone()[0],0)

    def test_creation_image_history_is_compact_and_owner_scoped(self):
        queued=jobs.submit(self.user,self.project,'original',{'source_id':D.uid(),'brief':{'platform':'xhs','topic':'咖啡','goal':'leads'},'temporary':'产品事实'})
        jobs.run(queued)
        inline='data:image/png;base64,'+base64.b64encode(b'x'*5000).decode()
        with D.db() as c:
            creation=c.execute('SELECT id FROM creation_outputs WHERE project_id=?',(self.project,)).fetchone()[0]
            image=D.uid();remote=D.uid()
            for ident,url in ((image,inline),(remote,'https://images.example/historical.png')):
                c.execute('INSERT INTO generated_images VALUES (?,?,?,?,?,?)',(ident,self.project,creation,D.dumps({'url':url}),None,D.now()))
        result=self.client.req('/api/creations/'+creation+'/images?project_id='+self.project)
        self.assertEqual(result[0],200);self.assertEqual(len(result[1]),2)
        self.assertNotIn('base64',json.dumps(result[1]));self.assertLess(len(json.dumps(result[1])),2000)
        self.assertEqual(self.client.req('/api/images/'+remote+'?project_id='+self.project)[1]['data']['url'],'https://images.example/historical.png')
        other=Client(self.client.base)
        self.assertEqual(other.req('/api/images/'+image+'?project_id='+self.project)[0],401)
        foreign=self.client.req('/api/projects','POST',{'name':'另一个空间'})[1]['id']
        self.assertEqual(self.client.req('/api/images/'+image+'?project_id='+foreign)[0],404)
        self.assertEqual(self.client.req('/api/creations/'+creation+'/images?project_id='+foreign)[0],404)


if __name__=='__main__':unittest.main()
