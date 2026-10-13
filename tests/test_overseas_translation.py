import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import overseas_translation as translation, overseas_library

D=importlib.import_module('server.db')


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=D.DB_PATH
        D.DB_PATH=str(Path(self.temp.name)/'db.sqlite')
        D.init()

    def tearDown(self):
        D.DB_PATH=self.original
        self.temp.cleanup()

    def test_reviewed_title_and_original_remain_separate(self):
        item={'title':'The World’s Worst Robbers','summary':'The World’s Worst Robbers','reference_video':{'title':'The World’s Worst Robbers','publisher':'Daniel LaBelle'}}
        result=translation.enrich(item)
        self.assertEqual(result['title_zh'],'世界上最笨的劫匪')
        self.assertEqual(result['summary_zh'],result['title_zh'])
        self.assertEqual(result['reference_video']['title_zh'],result['title_zh'])
        self.assertEqual(result['title'],item['title'])
        self.assertNotIn('title_zh',item)
        self.assertEqual(result['reference_video']['publisher'],'Daniel LaBelle')

    def test_all_sixty_reference_titles_have_chinese(self):
        self.assertEqual(len(overseas_library.REFERENCE_VIDEOS),60)
        for video in overseas_library.REFERENCE_VIDEOS.values():
            self.assertIn('title_zh',translation.enrich({'reference_video':video})['reference_video'])

    def test_cache_survives_init_and_invalidates_changed_source(self):
        with D.db() as c:c.execute('INSERT INTO overseas_translations VALUES (?,?,?)',(translation.key('A new story'),'一个新故事',D.now()))
        D.init()
        item={'title':'A new story','summary':'中文说明','title_zh':'伪造旧翻译'}
        self.assertEqual(translation.enrich(item)['title_zh'],'一个新故事')
        self.assertNotIn('summary_zh',translation.enrich(item))
        self.assertNotIn('title_zh',translation.enrich({**item,'title':'Another new story'}))

    def test_unavailable_translator_preserves_source_without_request_work(self):
        with patch.object(translation,'RUNNING',False),patch.object(translation,'translate_batch') as invoke:
            original={'title':'Unknown new story','summary':'Full original caption'}
            self.assertEqual(translation.enrich(original),original)
            invoke.assert_not_called()

    @unittest.skipUnless(translation.RUNTIME.exists() and all((translation.ROOT/'data/translation-models'/pair/'model/model.bin').exists() for pair in ('en_zh','fr_en','de_en','es_en')), 'Optional local language models not installed')
    def test_real_local_models_translate_new_text_in_all_installed_languages(self):
        texts=['A new short video with an unexpected ending. 🎀 #story @creator',
               'Je teste un produit pour nettoyer la cuisine.',
               'Ein Mann kommt mit einer überraschenden Idee.',
               'Un vídeo corto con un final inesperado.']
        results=translation.translate_batch(texts)
        for value in results:self.assertRegex(value,r'[\u4e00-\u9fff]')
        for value in ('🎀','#story','@creator'):self.assertIn(value,results[0])

    def test_background_result_is_cached_and_failure_can_retry(self):
        text='A new arriving caption'
        translation.PENDING.put(text)
        translation.QUEUED.add(text)
        with patch.object(translation,'translate_batch',return_value=['一条新发布的文案']):self.assertTrue(translation.drain())
        self.assertEqual(translation.enrich({'title':text})['title_zh'],'一条新发布的文案')
        text='An unavailable caption'
        translation.PENDING.put(text);translation.QUEUED.add(text)
        with patch.object(translation,'translate_batch',side_effect=OSError()):self.assertTrue(translation.drain())
        self.assertNotIn('title_zh',translation.enrich({'title':text}))
        self.assertIn(text,translation.FAILED)

    def test_chinese_keyword_search_and_saved_note_keep_exact_translation(self):
        with D.db() as c:
            c.execute('INSERT INTO overseas_feed_videos VALUES (?,?,?,?,?,?)',('feed_test','https://www.tiktok.com/@test/video/1234567890123456789',json.dumps({'id':'feed_test','title':'The World’s Worst Robbers','summary':'The World’s Worst Robbers','url':'https://www.tiktok.com/@test/video/1234567890123456789','platform':'tiktok','category':'','published_at':D.now(),'source_kind':'daily_feed'}),D.now(),D.now(),D.now()))
        with patch.object(overseas_library,'list_ideas',return_value=[]):
            items=overseas_library.recommendations('unused',query='劫匪',platform='tiktok')
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['title_zh'],'世界上最笨的劫匪')
        self.assertEqual(translation.public_items()[0]['id'],'feed_test')
