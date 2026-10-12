import copy
import json
import unittest
from unittest.mock import patch
from tests import test_original as fixture
from tests.test_app import Client
from server import overseas, overseas_library, adapters


class OverseasApiTests(unittest.TestCase):
    setUp=fixture.OriginalTests.setUp
    tearDown=fixture.OriginalTests.tearDown
    post=fixture.OriginalTests.post
    run_task=fixture.OriginalTests.run_task
    ws=fixture.OriginalTests.ws

    def create(self,**kwargs):
        status,result=self.post('/api/overseas/create',{'platform':'overseas','topic':'Foldable charger',**kwargs})
        self.assertEqual(status,202,result)
        self.assertEqual(self.run_task(result)[0]['state'],'SUCCEEDED')
        return result

    def ideas(self,query=''):
        return self.c.req('/api/overseas/ideas?project_id='+self.p+query)

    def test_skill_import_and_existing_config_migration_is_idempotent(self):
        with fixture.D.db() as c:
            names={r['name'] for r in c.execute("SELECT * FROM skill_versions WHERE status='Published'")}
            self.assertTrue({p+'_original' for p in overseas.PLATFORMS}<=names)
            count=c.execute('SELECT count(*) FROM skill_versions').fetchone()[0]
        fixture.D.init()
        with fixture.D.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM skill_versions').fetchone()[0],count)
            cfg=json.loads(c.execute("SELECT value FROM settings WHERE key='tikhub'").fetchone()[0])
            self.assertEqual(cfg['endpoints']['instagram_search']['params'],{'keyword':'{text}'})

    def test_v22_upgrade_archives_previous_prompt_and_only_runs_once(self):
        marker='skill_release_2026_10_12_hiccai_pop_2_2_f7c717f'
        with fixture.D.db() as c:
            c.execute('DELETE FROM settings WHERE key=?',(marker,))
            c.execute("UPDATE skill_versions SET prompt='old overseas method' WHERE name='overseas_original' AND status='Published'")
        fixture.D.init()
        with fixture.D.db() as c:
            current=c.execute("SELECT * FROM skill_versions WHERE name='overseas_original' AND status='Published'").fetchone()
            self.assertIn('version: 2.2.0',current['prompt'])
            self.assertEqual(c.execute("SELECT status FROM skill_versions WHERE prompt='old overseas method'").fetchone()[0],'Archived')
            c.execute("UPDATE skill_versions SET prompt='admin edited prompt' WHERE id=?",(current['id'],))
        fixture.D.init()
        with fixture.D.db() as c:
            self.assertEqual(c.execute("SELECT prompt FROM skill_versions WHERE name='overseas_original' AND status='Published'").fetchone()[0],'admin edited prompt')

    def test_archetypes_recommendation_save_and_project_isolation(self):
        status,result=self.ideas()
        self.assertEqual(status,200)
        self.assertEqual(len(result['items']),60)
        self.assertTrue(all(not i['url'] and not i['metrics'] for i in result['items']))
        self.assertFalse(result['search_available'])
        self.assertEqual(set(result['categories']),set('ABCDEFGH'))
        filtered=self.ideas('&query=charger')[1]['items']
        self.assertTrue(filtered)
        self.assertEqual(filtered[0]['title'],'三合一折叠无线充')
        self.assertIn('匹配关键词',filtered[0]['recommendation'])
        status,item=self.post('/api/overseas/ideas',{'archetype_id':'archetype_03'})
        self.assertEqual(status,200,item)
        self.assertTrue(item['saved'])
        self.assertEqual(len(self.ideas()[1]['items']),60)
        self.assertEqual(len(self.ideas('&saved=1')[1]['items']),1)
        # Duplicate collection updates the existing record.
        self.assertEqual(self.post('/api/overseas/ideas',{'archetype_id':'archetype_03'})[1]['id'],item['id'])
        p2=self.c.req('/api/projects','POST',{'name':'另一个项目'})[1]['id']
        self.assertEqual(self.c.req('/api/overseas/ideas?project_id='+p2+'&saved=1')[1]['items'],[])
        self.assertEqual(self.c.req('/api/overseas/ideas/'+item['id'],'PATCH',{'project_id':p2,'saved':False})[0],404)
        self.assertEqual(self.post('/api/overseas/create',{'platform':'tiktok','topic':'Charger','reference_id':item['id'],'project_id':p2})[0],404)

    def test_manual_collection_canonical_links_and_no_fabricated_metrics(self):
        status,item=self.post('/api/overseas/ideas',{'url':'https://youtu.be/abcdefghijk?utm_source=test','title':'Example','summary':'Before/after contrast','metrics':{'views':9999},'source_kind':'data_source'})
        self.assertEqual(status,200,item)
        self.assertEqual(item['url'],'https://www.youtube.com/watch?v=abcdefghijk')
        self.assertEqual(item['source_kind'],'manual')
        self.assertEqual(item['metrics'],{})
        self.assertEqual(self.post('/api/overseas/ideas',{'url':'https://www.youtube.com/shorts/abcdefghijk','title':'Duplicate'})[1]['id'],item['id'])
        for url in ('https://tiktok.com.evil.test/@a/video/123','http://www.tiktok.com/@a/video/123','https://www.instagram.com/account','https://127.0.0.1/a','javascript:alert(1)','https://www.youtube.com/watch?v=short'):
            self.assertEqual(self.post('/api/overseas/ideas',{'url':url,'title':'test'})[0],400,url)
        self.assertEqual(self.post('/api/overseas/ideas',{'archetype_id':'archetype_99'})[0],400)

    def test_default_three_platform_production_repeat_credits_export(self):
        before=self.c.req('/api/bootstrap')[1]['credits']['balance']
        result=self.create()
        outs=self.ws()['creations']
        self.assertEqual(len(outs),3)
        self.assertEqual({o['data']['overseas']['platform'] for o in outs},{'tiktok','instagram','youtube'})
        self.assertTrue(all(o['data']['demo'] for o in outs))
        self.assertTrue(all(len(o['data']['hooks'])==3 for o in outs))
        self.assertEqual(len({o['data']['first_second'] for o in outs}),3)
        self.assertEqual(len({o['data']['reveal'] for o in outs}),3)
        self.assertTrue(all(o['data']['shots'][-1]['end']==24 for o in outs))
        self.assertEqual(self.c.req('/api/bootstrap')[1]['credits']['balance'],before-15)
        status,again=self.post('/api/overseas/create',{'brief_id':result['brief_id']})
        self.assertEqual(status,202,again)
        self.assertEqual(self.run_task(again)[0]['state'],'SUCCEEDED')
        self.assertEqual(len(self.ws()['creations']),6)
        self.assertEqual(len({o['data']['title'] for o in self.ws()['creations']}),6)
        status,export=self.c.req('/api/export?project_id='+self.p,raw=True)
        self.assertEqual(status,200)
        self.assertIn('Foldable charger',export.decode())

    def test_platform_language_duration_and_reference_inheritance(self):
        item=self.post('/api/overseas/ideas',{'archetype_id':'archetype_03'})[1]
        result=self.create(platform='instagram',market='Germany',language='de-zh',duration=32,temporary='折叠式无线充，支持三种设备。',reference_id=item['id'])
        self.assertTrue(all(o['data']['overseas']['platform']=='instagram' for o in self.ws()['creations']))
        brief=self.ws()['briefs'][0]['data']
        self.assertEqual(brief['language'],'de-zh')
        self.assertEqual(brief['reference_snapshot']['title'],item['title'])
        status,again=self.post('/api/overseas/create',{'brief_id':result['brief_id']})
        self.run_task(again)
        self.assertTrue(all(o['data']['overseas']['duration']==32 for o in self.ws()['creations']))

    def test_invalid_input_and_unconfigured_search_do_not_charge(self):
        before=self.c.req('/api/bootstrap')[1]['credits']
        for change in ({'platform':'xhs'},{'language':'unsupported'},{'duration':True},{'duration':99},{'market':[]},{'reference_id':'badid'},{'assets':[' чужой ']}):
            status,_=self.post('/api/overseas/create',{'platform':'tiktok','topic':'Charger',**change})
            self.assertIn(status,(400,404),change)
        status,message=self.post('/api/overseas/search',{'platform':'tiktok','query':'charger'})
        self.assertEqual(status,400)
        self.assertIn('未启用',message['error'])
        self.assertEqual(self.c.req('/api/bootstrap')[1]['credits'],before)

    def test_real_model_receives_skill_reference_context_and_source_checks(self):
        captured=[]
        asset=self.post('/api/assets',{'name':'charger','kind':'产品信息','content':'产品支持三种设备，采用折叠结构。'})[1]['id']
        with fixture.D.db() as c:c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        def fake(prompt,schema,version,kind,validator):
            captured.append((copy.deepcopy(prompt),version,kind))
            outputs=overseas.demo_outputs(prompt['brief'],prompt['assets'],prompt['batch'])
            for o in outputs:
                o.pop('demo');o['missing']=[]
                o['evidence']=[{'asset_id':asset,'quote':'采用折叠结构'}]
            validator({'outputs':outputs})
            return {'outputs':outputs},'fake/model'
        with patch.object(adapters,'model_json',side_effect=fake):
            self.create(platform='tiktok',assets=[asset],language='en-zh',reference_id='archetype_03')
        prompt,skill,kind=captured[0]
        self.assertIn('hiccai-pop v2.2',skill)
        self.assertIn('公平伏笔',skill)
        self.assertEqual(kind,'create')
        self.assertEqual(prompt['reference']['examples'][0]['id'],'archetype_03')
        self.assertEqual(prompt['assets'][0]['id'],asset)
        self.assertEqual(prompt['language'],'English')
        self.assertTrue(all(not o['data'].get('demo') for o in self.ws()['creations']))

    def test_search_real_response_dedup_cache_and_unknown_metrics(self):
        raw={'data':{'item_list':[{'id':'12345','desc':'foldable charging station','author':{'uniqueId':'brand'},'stats':{'playCount':1000,'diggCount':0}}]}}
        with fixture.D.db() as c:
            c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
            cfg=json.loads(c.execute("SELECT value FROM settings WHERE key='tikhub'").fetchone()[0]);cfg['api_key']='test-only-key'
            c.execute("UPDATE settings SET value=? WHERE key='tikhub'",(json.dumps(cfg),))
        with patch.object(adapters.TikHubAdapter,'call',return_value=raw) as call:
            status,result=self.post('/api/overseas/search',{'platform':'tiktok','query':'charger'})
            self.assertEqual(status,200,result)
            self.assertEqual(result['items'][0]['metrics'],{'views':1000,'likes':0})
            self.assertFalse(result['items'][0]['saved'])
            self.assertTrue(self.post('/api/overseas/search',{'platform':'tiktok','query':'charger'})[1]['cached'])
            self.assertEqual(call.call_count,1)
        item=result['items'][0]
        self.assertEqual(self.c.req('/api/overseas/ideas/'+item['id'],'PATCH',{'project_id':self.p,'saved':True})[0],200)
        self.assertEqual(len(self.ideas('&saved=1')[1]['items']),1)

    def test_uploaded_document_and_poster_reach_overseas_model(self):
        from tests.test_documents import docx, data_url
        status,extracted=self.c.req('/api/extract','POST',{'name':'品牌资料.docx','data':data_url(docx())})
        self.assertEqual(status,200,extracted)
        document=self.post('/api/assets',{'name':'品牌资料.docx','kind':'产品信息','content':extracted['text']})[1]['id']
        photo='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a2uoAAAAASUVORK5CYII='
        status,poster=self.post('/api/assets',{'name':'产品海报.png','kind':'图片','content':photo})
        self.assertEqual(status,200,poster)
        with fixture.D.db() as c:c.execute("UPDATE settings SET value='\"live\"' WHERE key='mode'")
        captured=[]
        def fake(payload,schema,prompt,kind,validator):
            captured.extend(payload['assets'])
            outputs=overseas.demo_outputs(payload['brief'],payload['assets'],1)
            validator({'outputs':outputs})
            return {'outputs':outputs},'test/model'
        with patch.object(adapters,'model_json',side_effect=fake):
            self.create(assets=[document,poster['id']])
        self.assertEqual({a['id'] for a in captured},{document,poster['id']})
        self.assertEqual(next(a['content'] for a in captured if a['id']==poster['id']),photo)
        self.assertIn('山野咖啡',next(a['content'] for a in captured if a['id']==document))
        self.assertIn('产品揭晓镜号',self.c.req('/api/export?project_id='+self.p,raw=True)[1].decode())


class OverseasStructureTests(unittest.TestCase):
    def setUp(self):
        self.brief={'platform':'overseas','topic':'charger','goal':'leads','market':'US','duration':24,'language':'en-zh'}
        self.outputs=overseas.demo_outputs(self.brief,[],1)

    def test_coverage_hooks_bilingual_and_originality_are_checked(self):
        overseas.validate({'outputs':self.outputs},self.brief,[])
        for mutate in (lambda o:o[0]['shots'][1].update(start=2),lambda o:o[0].update(translation_zh=''),lambda o:o[0]['hooks'].pop(),lambda o:o[0].update(script=o[1]['script']),lambda o:o[0].update(target_platform='youtube'),lambda o:o[0].update(evidence=[{'asset_id':'other','quote':'not provided'}]),lambda o:o[0].update(clue=''),lambda o:o[0]['shots'][0].update(implementation=''),lambda o:o[0].update(ending_type='悬念')):
            outputs=copy.deepcopy(self.outputs);mutate(outputs)
            with self.assertRaises(ValueError):overseas.validate({'outputs':outputs},self.brief,[])

    def test_provider_shapes_and_safe_canonical_urls(self):
        instagram=overseas_library.normalize({'data':{'items':[{'media':{'code':'abc123','caption':{'text':'Kitchen reveal'},'like_count':15}}]}},'instagram')
        self.assertEqual(instagram[0]['url'],'https://www.instagram.com/reel/abc123')
        youtube=overseas_library.normalize({'videoRenderer':{'videoId':'abcdefghijk','title':{'runs':[{'text':'Coffee shorts'}]}}},'youtube')
        self.assertEqual(youtube[0]['title'],'Coffee shorts')
        self.assertEqual(youtube[0]['metrics'],{})

    def test_final_reveal_and_casting_are_checked(self):
        for change in ({'reveal_shot':1},{'reveal_shot':True},{'casting':'不露脸'}):
            outputs=copy.deepcopy(self.outputs);outputs[0].update(change)
            with self.assertRaises(ValueError):overseas.validate({'outputs':outputs},self.brief,[])

    def test_different_titles_cannot_hide_the_same_creative_direction(self):
        for field in ('angle','first_second','misread','reveal'):
            outputs=copy.deepcopy(self.outputs)
            outputs[1][field]=outputs[0][field]
            with self.assertRaisesRegex(ValueError,'方案不能重复'):
                overseas.validate({'outputs':outputs},self.brief,[])
