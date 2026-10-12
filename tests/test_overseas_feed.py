import concurrent.futures
import json
import os
import threading
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape
from tests import test_original as fixture
from server import overseas_feed as feed, overseas_library

SOURCE=feed.YOUTUBE_SOURCES[0]
DAY='2026-10-12T15:00:00+00:00'


def atom(entries, source=SOURCE):
    return (f'<feed xmlns="{feed.NS["a"]}" xmlns:yt="{feed.NS["y"]}" xmlns:media="{feed.NS["m"]}">'
            f'<yt:channelId>{source["channel_id"][2:]}</yt:channelId>'+''.join(
                f'<entry><yt:videoId>{ident}</yt:videoId><title>{escape(title)}</title><published>{published}</published>'
                f'<author><name>Real publisher</name></author><media:group><media:description>{escape(description)}</media:description></media:group></entry>'
                for ident,title,published,description in entries)+'</feed>').encode()


OLD=('abcdefghijk','Charger unfolds','2026-10-10T14:00:00Z','Three devices charge on one desk.')
NEW=('newvideoxyz','A new charging idea','2026-10-13T14:00:00Z','A small charger transforms the desk.')


def tiktok_html(source,entries):
    data={'source':{'data':{'/embed/@'+source['handle']:{'userInfo':{'uniqueId':source['handle'],'nickname':source['publisher'],'privateAccount':False},'videoList':entries}}}}
    return ('<script id="__FRONTITY_CONNECT_STATE__" type="application/json">'+json.dumps(data)+'</script>').encode()


def tiktok_entry(source,ident='7680599033039179038',caption='An unexpected ending'):
    return {'id':ident,'desc':caption,'authorUniqueId':source['handle'],'height':1280,'width':720,'coverUrl':'https://example.com/cover.jpg'}


def detail_html(item,duration=33,created=1791817200):
    detail={'id':item['url'].rsplit('/',1)[-1],'author':{'uniqueId':item['url'].split('/@',1)[1].split('/')[0]},'video':{'duration':duration},'createTime':str(created)}
    return ('<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__">'+json.dumps({'__DEFAULT_SCOPE__':{'webapp.video-detail':{'itemInfo':{'itemStruct':detail}}}})+'</script>').encode()


class DailyVideoTests(unittest.TestCase):
    setUp=fixture.OriginalTests.setUp
    tearDown=fixture.OriginalTests.tearDown
    post=fixture.OriginalTests.post
    ws=fixture.OriginalTests.ws
    run_task=fixture.OriginalTests.run_task

    def sync(self,blob,day=DAY,force=False):
        with patch.object(feed,'SOURCES',[SOURCE]),patch.object(feed,'now',return_value=day),patch.object(feed,'fetch',return_value=blob):
            return feed.refresh(force=force,background=False)

    def test_daily_sync_adds_real_new_entries_and_orders_by_publication(self):
        first=self.sync(atom([OLD]))
        self.assertEqual((first['state'],first['added_count'],first['pool_size']),('succeeded',1,1))
        with patch.object(feed,'SOURCES',[SOURCE]),patch.object(feed,'now',return_value=DAY),patch.object(feed,'fetch') as fetch:
            self.assertTrue(feed.refresh(background=False)['cached'])
            self.assertTrue(feed.refresh(force=True,background=False)['cached'])
            fetch.assert_not_called()
        second=self.sync(atom([OLD,NEW]),'2026-10-13T15:00:00+00:00')
        self.assertEqual((second['added_count'],second['changed_count'],second['pool_size']),(1,0,2))
        items=overseas_library.recommendations(self.p)
        self.assertEqual([i['title'] for i in items[:2]],[NEW[1],OLD[1]])
        self.assertEqual(items[0]['reference_video']['publisher'],'Real publisher')
        self.assertEqual(items[0]['reference_video']['relation'],'来源视频')
        self.assertEqual(items[0]['metrics'],{})
        with fixture.D.db() as c:
            self.assertEqual(c.execute('SELECT created_at FROM overseas_feed_videos WHERE url=?',('https://www.youtube.com/watch?v=abcdefghijk',)).fetchone()[0],DAY)

    def test_repeated_content_does_not_fake_new_entries_or_updated_time(self):
        first=self.sync(atom([OLD]))
        result=self.sync(atom([OLD]),'2026-10-13T15:00:00+00:00')
        self.assertEqual((result['added_count'],result['changed_count']),(0,0))
        self.assertEqual(result['last_updated_at'],first['last_updated_at'])
        self.assertEqual(result['last_checked_at'],'2026-10-13T15:00:00+00:00')
        fixture.D.init()
        self.assertEqual(feed.status()['last_updated_at'],first['last_updated_at'])

    def test_daily_boundary_uses_configured_timezone(self):
        with patch.dict(os.environ,{'DAOLOOK_FEED_TIMEZONE':'America/New_York'}):
            self.sync(atom([OLD]),'2026-10-13T03:00:00+00:00')
            result=self.sync(atom([OLD]),'2026-10-13T05:00:00+00:00')
        self.assertFalse(result['cached'])
        self.assertEqual(result['last_checked_at'],'2026-10-13T05:00:00+00:00')

    def test_failed_refresh_preserves_successful_cache_and_time(self):
        first=self.sync(atom([OLD]))
        with patch.object(feed,'SOURCES',[SOURCE]),patch.object(feed,'now',return_value='2026-10-13T15:00:00+00:00'),patch.object(feed,'fetch',side_effect=OSError('unavailable')):
            result=feed.refresh(background=False)
        self.assertEqual(result['state'],'failed')
        self.assertEqual(result['pool_size'],1)
        self.assertEqual(result['last_checked_at'],first['last_checked_at'])
        self.assertEqual(result['last_updated_at'],first['last_updated_at'])

    def test_partial_refresh_keeps_successes_and_retries_after_one_hour(self):
        other={**SOURCE,'channel_id':feed.YOUTUBE_SOURCES[1]['channel_id'],'publisher':'Second publisher'}
        def fetch(source):
            if source['publisher']=='Second publisher':raise OSError('unavailable')
            return atom([OLD])
        with patch.object(feed,'SOURCES',[SOURCE,other]),patch.object(feed,'now',return_value=DAY),patch.object(feed,'fetch',side_effect=fetch):
            result=feed.refresh(background=False)
            self.assertEqual((result['state'],result['successful_sources'],result['pool_size']),('partial',1,1))
            self.assertEqual(result['errors'],['Second publisher'])
            self.assertTrue(feed.refresh(background=False)['cached'])
        with patch.object(feed,'SOURCES',[SOURCE,other]),patch.object(feed,'now',return_value='2026-10-12T16:01:00+00:00'),patch.object(feed,'fetch',side_effect=lambda s:atom([OLD],s)):
            self.assertEqual(feed.refresh(background=False)['state'],'succeeded')

    def test_simultaneous_refreshes_share_one_persistent_run(self):
        started=threading.Event();release=threading.Event()
        def fetch(source):
            started.set();release.wait(3)
            return atom([OLD])
        with patch.object(feed,'SOURCES',[SOURCE]),patch.object(feed,'now',return_value=DAY),patch.object(feed,'fetch',side_effect=fetch) as call:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                pending=pool.submit(feed.refresh,False,False)
                self.assertTrue(started.wait(2))
                try:
                    second=feed.refresh(force=True,background=False)
                    self.assertTrue(second['cached'])
                    self.assertEqual(second['state'],'running')
                finally:release.set()
                self.assertEqual(pending.result()['state'],'succeeded')
            self.assertEqual(call.call_count,1)

    def test_interrupted_sync_can_recover_after_lease_expiry(self):
        with fixture.D.db() as c:
            c.execute('UPDATE overseas_feed_state SET data=? WHERE id=1',(json.dumps({'state':'running','run_id':'expired','last_attempt_at':'2026-10-12T14:49:00+00:00'}),))
        result=self.sync(atom([OLD]))
        self.assertEqual(result['state'],'succeeded')
        self.assertEqual(result['added_count'],1)

    def test_global_references_and_private_collections_and_generation_snapshot(self):
        self.sync(atom([OLD]))
        idea=feed.videos()[0]
        self.assertEqual(overseas_library.reference(self.p,idea['id'])['url'],idea['url'])
        status,saved=self.post('/api/overseas/ideas',{'feed_id':idea['id'],'title':'Forged title','metrics':{'views':999}})
        self.assertEqual(status,200)
        self.assertEqual(saved['title'],OLD[1])
        self.assertTrue(saved['saved'])
        p2=self.c.req('/api/projects','POST',{'name':'Other project'})[1]['id']
        self.assertEqual(self.c.req('/api/overseas/ideas?project_id='+p2+'&saved=1')[1]['items'],[])
        self.assertEqual(overseas_library.recommendations(p2)[0]['feed_id'],idea['id'])
        self.assertIsNone(overseas_library.reference(p2,saved['id']))
        self.assertEqual(self.post('/api/overseas/ideas',{'feed_id':'feed_missing'})[0],400)
        task=self.post('/api/overseas/create',{'platform':'tiktok','topic':'Charger','reference_id':idea['id']})[1]
        self.assertEqual(self.run_task(task)[0]['state'],'SUCCEEDED')
        snapshot=self.ws()['briefs'][0]['data']['reference_snapshot']
        self.assertEqual(snapshot['url'],idea['url'])
        self.assertEqual(snapshot['reference_video'],idea['reference_video'])
        self.assertEqual(len({(i.get('reference_video') or {}).get('url') or i['url'] for i in overseas_library.recommendations(self.p)}),len(overseas_library.recommendations(self.p)))

    def test_tiktok_defaults_and_source_change_keep_optional_youtube_references(self):
        self.sync(atom([OLD]))
        source=feed.SOURCES[-1]
        with patch.object(feed,'SOURCES',[source]),patch.object(feed,'now',return_value=DAY),patch.object(feed,'fetch',return_value=tiktok_html(source,[tiktok_entry(source)])),patch.object(feed,'fetch_page',side_effect=lambda url:detail_html({'url':url})):
            result=feed.refresh(background=False)
        self.assertFalse(result['cached'])
        self.assertEqual(result['added_count'],1)
        public=self.c.req('/api/overseas/ideas?project_id='+self.p)[1]['items']
        self.assertEqual(len(public),1)
        self.assertTrue(all(i['reference_video']['platform']=='tiktok' for i in public))
        self.assertEqual(public[0]['duration'],33)
        self.assertEqual(len(overseas_library.recommendations(self.p,platform='youtube')),61)
        self.assertEqual(overseas_library.recommendations(self.p)[0]['platform'],'tiktok')
        saved=self.post('/api/overseas/ideas',{'feed_id':public[0]['id']})[1]
        # Signed covers refresh without replacing a private collection's creative text.
        with fixture.D.db() as c:
            row=json.loads(c.execute('SELECT data FROM overseas_ideas WHERE id=?',(saved['id'],)).fetchone()[0])
            row['summary']='My own creative note'
            c.execute('UPDATE overseas_ideas SET data=? WHERE id=?',(json.dumps(row),saved['id']))
            current=json.loads(c.execute('SELECT data FROM overseas_feed_videos WHERE id=?',(public[0]['id'],)).fetchone()[0])
            current['reference_video']['thumbnail']='https://example.com/refreshed-cover.jpg'
            c.execute('UPDATE overseas_feed_videos SET data=? WHERE id=?',(json.dumps(current),public[0]['id']))
        hydrated=overseas_library.reference(self.p,saved['id'])
        self.assertEqual(hydrated['summary'],'My own creative note')
        self.assertEqual(hydrated['reference_video']['thumbnail'],'https://example.com/refreshed-cover.jpg')

    def test_pruning_old_public_pool_retains_saved_reference(self):
        self.sync(atom([OLD]))
        item=self.post('/api/overseas/ideas',{'feed_id':feed.videos()[0]['id']})[1]
        self.sync(atom([OLD]),'2027-05-12T15:00:00+00:00')
        self.assertEqual(feed.videos(),[])
        self.assertEqual(overseas_library.reference(self.p,item['id'])['title'],OLD[1])

    def test_refresh_api_returns_status_without_charging_or_reading_other_projects(self):
        before=self.c.req('/api/bootstrap')[1]['credits']
        with patch.object(feed,'refresh',return_value={'state':'running','daily':True}) as refresh:
            status,result=self.post('/api/overseas/refresh',{})
            self.assertEqual((status,result['state']),(200,'running'))
            refresh.assert_called_once_with(force=True)
            self.assertEqual(self.post('/api/overseas/refresh',{'project_id':'unknown'})[0],404)
            self.assertEqual(refresh.call_count,1)
        self.assertEqual(self.c.req('/api/bootstrap')[1]['credits'],before)
        self.assertIn('refresh',self.c.req('/api/overseas/ideas?project_id='+self.p)[1])


class FeedParsingTests(unittest.TestCase):
    def test_tiktok_filters_private_horizontal_and_generic_reviews(self):
        source=feed.SOURCES[0]
        valid=tiktok_entry(source,ident='7694716128580357398',caption='Adam and Eve get evicted')
        entries=[valid,{**valid,'privateItem':True},{**valid,'id':'7694716128580357399','width':1920,'height':1080},
                 {**valid,'id':'7694716128580357400','desc':'New charger unboxing review'},
                 {**valid,'id':'7694716128580357401','authorUniqueId':'another_person'}]
        items=feed.parse(tiktok_html(source,entries),source)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['reference_video']['platform'],'tiktok')
        self.assertNotIn('published_at',items[0])
        self.assertEqual(items[0]['metrics'],{})
        self.assertEqual(items[0]['url'],'https://www.tiktok.com/@adrianbliss/video/7694716128580357398')

    def test_tiktok_duration_and_timestamp_require_real_provider_metadata(self):
        source=feed.SOURCES[0]
        item=feed.parse(tiktok_html(source,[tiktok_entry(source)]),source)[0]
        with patch.object(feed,'reference',return_value=None),patch.object(feed,'now',return_value=DAY):
            for duration,created in ((120,1791817200),(30,1600000000),(30,1890000000)):
                with patch.object(feed,'fetch_page',return_value=detail_html(item,duration,created)):
                    self.assertIsNone(feed.tiktok_details(item))
            with patch.object(feed,'fetch_page',return_value=detail_html(item)):
                accepted=feed.tiktok_details(item)
        self.assertEqual(accepted['duration'],33)
        self.assertEqual(accepted['reference_video']['published_at'],accepted['published_at'])
        previous={**accepted,'summary':'Old caption'}
        changed={**item,'summary':'New caption'}
        with patch.object(feed,'reference',return_value=previous),patch.object(feed,'now',return_value=DAY),patch.object(feed,'fetch_page') as fetch:
            self.assertEqual(feed.tiktok_details(changed)['summary'],'New caption')
            fetch.assert_not_called()

    def test_tiktok_sources_are_story_and_brand_accounts(self):
        self.assertTrue(all(s['platform']=='tiktok' for s in feed.SOURCES))
        self.assertEqual(len({s['handle'] for s in feed.SOURCES}),len(feed.SOURCES))
        self.assertTrue({'adrianbliss','liquiddeath','scrubdaddy'}<={s['handle'] for s in feed.SOURCES})

    def test_brand_promotions_do_not_fill_the_story_recommendations(self):
        source=next(s for s in feed.SOURCES if s['handle']=='scrubdaddy')
        entries=[tiktok_entry(source,'7694716128580357398','Grab our new product on Amazon today'),
                 tiktok_entry(source,'7694716128580357399','Date a Daddy they said…'),
                 tiktok_entry(source,'7694716128580357400','Unexpected gift! No purchase necessary. Official rules apply.')]
        items=feed.parse(tiktok_html(source,entries),source)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['summary'],'Date a Daddy they said…')

    def test_parser_rejects_wrong_channels_entities_stale_future_and_invalid_ids(self):
        entries=[OLD,OLD,('bad','Invalid id','2026-10-10T14:00:00Z',''),('oldvideoxyz','Old','2020-10-10T14:00:00Z',''),NEW]
        with patch.object(feed,'now',return_value=DAY):
            items=feed.parse(atom(entries),SOURCE)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['url'],'https://www.youtube.com/watch?v=abcdefghijk')
        with patch.object(feed,'now',return_value=DAY):
            self.assertEqual(len(feed.parse(atom([OLD]).replace(SOURCE['channel_id'][2:].encode(),SOURCE['channel_id'].encode()),SOURCE)),1)
        with self.assertRaises(ValueError):feed.parse(atom([OLD],{**SOURCE,'channel_id':'UC'+'x'*22}),SOURCE)
        with self.assertRaises(ValueError):feed.parse(b'<!DOCTYPE feed><feed/>',SOURCE)
        with self.assertRaises(ValueError):feed.fetch({**SOURCE,'channel_id':'../../private'})

    def test_parser_keeps_unique_descriptions_and_omits_repeated_boilerplate(self):
        entries=[(str(i)*11,'Product '+str(i),'2026-10-10T14:00:00Z','A different scene '+str(i)+'\n\nShared brand boilerplate\n\nhttps://example.com/shop\n\n#brand') for i in range(4)]
        with patch.object(feed,'now',return_value=DAY):items=feed.parse(atom(entries),SOURCE)
        self.assertEqual(len(items),4)
        self.assertEqual(items[0]['summary'],'A different scene 0')

    def test_verified_sources_cover_every_product_category(self):
        self.assertEqual({s['category'] for s in feed.YOUTUBE_SOURCES},set('ABCDEFGH'))
        self.assertEqual(len({s['channel_id'] for s in feed.YOUTUBE_SOURCES}),len(feed.YOUTUBE_SOURCES))
        for source in feed.YOUTUBE_SOURCES:
            self.assertRegex(source['channel_id'],r'^UC[A-Za-z0-9_-]{22}$')
            self.assertEqual(source['feed_url'],'https://www.youtube.com/feeds/videos.xml?channel_id='+source['channel_id'])

    def test_product_titles_override_broad_channel_categories(self):
        self.assertEqual(feed.category('Travel Packing Cubes Organizer Set Review',SOURCE),'C')
        self.assertEqual(feed.category('IKEA Tote Bag Review',SOURCE),'E')
        self.assertEqual(feed.category('USB Charger Review',SOURCE),'A')
