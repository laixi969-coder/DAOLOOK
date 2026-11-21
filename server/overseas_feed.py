"""Daily public video discovery shared by projects; collections remain private."""
import concurrent.futures
import datetime
import gzip
import hashlib
import json
import os
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo
from .db import db, dumps, now, uid
from .adapters import NoCredentialRedirect, read_bounded, walk
from . import overseas_daily, overseas_translation, overseas_visuals

RESOURCE = Path(__file__).parent / 'resources/hiccai-pop'
YOUTUBE_SOURCES = json.loads((RESOURCE / 'daily-sources.json').read_text())
SOURCES = [{**entry, 'category':entry.get('category',''),
            'source_id':entry['platform']+':'+(entry.get('handle') or entry['channel_id'])}
           for entry in json.loads((RESOURCE / 'visual-sources.json').read_text())]
CASES = json.loads((RESOURCE / 'tiktok-cases.json').read_text())
NS = {'a':'http://www.w3.org/2005/Atom', 'y':'http://www.youtube.com/xml/schemas/2015', 'm':'http://search.yahoo.com/mrss/'}
MAX_AGE_DAYS = 180
SELECTION_VERSION = 3
STORY_CUES = r'\b(robbers?|robbery|waiter|evicted|exposed|uploading grandpa|not an egg|paging|date a daddy|plot twist|unexpected|turns out|what could go wrong|when|monsters?)\b'
CATEGORY_WORDS = {
    'A':('charger','charging','usb','iphone','phone','microphone','car mount'),
    'B':('nail','nails','mani','manis','lash','lashes','lipstick','makeup','hair','skin'),
    'C':('packing','laundry','storage','cleaning','scrubber','kitchen','air fryer','food','foods','cooking'),
    'D':('puppy','dog','cat','pet','chiot','chien','chat'),
    'E':('shirt','jacket','clothing','fashion','eyewear','glasses','bag','tote','heattech','uniqlo'),
    'F':('ferrofluid','fidget','toy','toys','magnetic field'),
    'G':('tool','tools','flashlight','camping','soldering','drill','saw'),
    'H':('screenbar','keyboard','desk','monitor','water filter','filter pitcher','lifestraw','door lock')}
CATEGORY_NAMES = {s['category']:s['category_name'] for s in YOUTUBE_SOURCES}


def category(title, source):
    scores={key:sum(bool(re.search(r'(?<!\w)'+re.escape(word)+r'(?!\w)',title.lower())) for word in words)
            for key,words in CATEGORY_WORDS.items()}
    best=max(scores,key=lambda key:(scores[key],key==source['category']))
    return best if scores[best] else source['category']


def timestamp(value):
    try:
        parsed=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed if parsed.tzinfo else None
    except (ValueError, AttributeError, TypeError):
        return None


def fetch(source):
    if source.get('platform')=='instagram':
        handle=source['handle']
        if not re.fullmatch(r'[A-Za-z0-9_.]{1,30}',handle):raise ValueError('Instagram 账号无效')
        return fetch_page('https://www.instagram.com/'+handle+'/embed/')
    if source.get('platform')=='tiktok':
        handle=source['handle']
        if not re.fullmatch(r'[A-Za-z0-9_.]{1,40}',handle):raise ValueError('TikTok账号无效')
        return fetch_page('https://www.tiktok.com/embed/@'+handle)
    channel=source['channel_id']
    if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',channel):
        raise ValueError('视频频道编号无效')
    # Only a fixed public YouTube endpoint is requested; no user URL or credentials.
    url='https://www.youtube.com/feeds/videos.xml?channel_id='+channel
    request=urllib.request.Request(url,headers={'User-Agent':'DAOLOOK/1.1','Accept':'application/atom+xml'})
    with urllib.request.build_opener(NoCredentialRedirect()).open(request,timeout=12) as response:
        return read_bounded(response,2*1024*1024,12)


def parse(blob, source):
    if source.get('platform')=='tiktok':return parse_tiktok(blob,source)
    if source.get('platform')=='instagram':return parse_instagram(blob,source)
    if b'<!DOCTYPE' in blob.upper() or b'<!ENTITY' in blob.upper():
        raise ValueError('视频订阅格式无效')
    root=ET.fromstring(blob)
    channel=root.findtext('y:channelId',namespaces=NS)
    if root.tag!='{'+NS['a']+'}feed' or channel not in (source['channel_id'],source['channel_id'][2:]):
        raise ValueError('视频订阅与频道不匹配')
    entries=root.findall('a:entry',NS)[:30]
    descriptions=[e.findtext('m:group/m:description','',NS).strip() for e in entries]
    blocks=[re.split(r'\n\s*\n',text) for text in descriptions]
    repeated=Counter(p.strip() for parts in blocks for p in set(parts) if p.strip())
    stamp=timestamp(now())
    cutoff=stamp-datetime.timedelta(days=MAX_AGE_DAYS)
    items=[];seen=set()
    for entry,parts in zip(entries,blocks):
        ident=entry.findtext('y:videoId','',NS)
        title=entry.findtext('a:title','',NS).strip()
        published=timestamp(entry.findtext('a:published','',NS))
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',ident) or ident in seen or not title or not published:
            continue
        if source.get('shorts_only') and not any(link.get('href')=='https://www.youtube.com/shorts/'+ident for link in entry.findall('a:link',NS)):
            continue
        published=published.astimezone(datetime.timezone.utc)
        if published<cutoff or published>stamp+datetime.timedelta(minutes=15):
            continue
        seen.add(ident)
        # Repeated channel boilerplate and link lists are not the video's description.
        useful=[p.strip() for p in parts if p.strip() and repeated[p.strip()]<max(3,len(entries)//2)
                and not re.fullmatch(r'[-=_\s]+',p) and not re.search(r'https?://',p) and not p.strip().startswith('#')]
        summary='\n\n'.join(useful)[:20000] or title
        url='https://www.youtube.com/watch?v='+ident
        publisher=entry.findtext('a:author/a:name',source['publisher'],NS).strip()[:200]
        video={'url':'https://www.youtube.com/shorts/'+ident if source.get('shorts_only') else url,'title':title,'publisher':publisher,'publisher_url':source['publisher_url'],
               'thumbnail':'https://i.ytimg.com/vi/'+ident+'/hqdefault.jpg','platform':'youtube',
               'source':'YouTube频道公开订阅','relation':'来源视频','published_at':published.isoformat()}
        feed_id='feed_'+hashlib.sha256(url.encode()).hexdigest()[:32]
        product_category=category(title,source)
        items.append({'id':feed_id,'feed_id':feed_id,'url':url,'title':title[:200],'summary':summary,
                      'channel_id':source['channel_id'],'platform':'youtube','category':product_category,'category_name':CATEGORY_NAMES.get(product_category,''),
                      'source_kind':'daily_feed','source':video['source'],'publisher':publisher,
                      'published_at':video['published_at'],'reference_video':video,'metrics':{}})
    return items


def fetch_page(url):
    # Request public provider pages using validated account and video identifiers.
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'gzip','Accept-Language':'en-US,en;q=0.8'})
    with urllib.request.build_opener(NoCredentialRedirect()).open(request,timeout=15) as response:
        if response.headers.get('Content-Encoding','').lower()=='gzip':
            with gzip.GzipFile(fileobj=response) as stream:return read_bounded(stream,6*1024*1024,45)
        return read_bounded(response,6*1024*1024,45)


def script_json(blob, ident):
    match=re.search(r'<script\b[^>]*\bid=["\']'+re.escape(ident)+r'["\'][^>]*>(.*?)</script>',blob.decode('utf-8'),re.S)
    if not match:raise ValueError('公开视频数据暂时不可用')
    return json.loads(match.group(1))


def instagram_context(blob):
    page=blob.decode('utf-8')
    match=re.search(r'"contextJSON"\s*:\s*',page)
    if not match:raise ValueError('Instagram 公开嵌入暂时不可用')
    encoded,_=json.JSONDecoder().raw_decode(page[match.end():])
    return json.loads(encoded)


def parse_instagram(blob, source):
    profile=instagram_context(blob)['context']
    handle=source['handle']
    if profile.get('username','').lower()!=handle.lower() or not isinstance(profile.get('graphql_media'),list):
        raise ValueError('Instagram 公开账号不匹配')
    items=[]
    stamp=timestamp(now())
    for wrapper in profile['graphql_media'][:12]:
        post=wrapper.get('shortcode_media') or {}
        code=post.get('shortcode','')
        dimensions=post.get('dimensions') or {}
        if (not re.fullmatch(r'[A-Za-z0-9_-]{5,24}',code) or not post.get('is_video') or
                (post.get('owner') or {}).get('username','').lower()!=handle.lower() or
                not 0<dimensions.get('width',0)<dimensions.get('height',0)):continue
        seconds=post.get('taken_at_timestamp')
        if type(seconds) is not int or not (stamp-datetime.timedelta(days=MAX_AGE_DAYS)).timestamp()<=seconds<=(stamp+datetime.timedelta(minutes=15)).timestamp():continue
        edges=(post.get('edge_media_to_caption') or {}).get('edges') or []
        caption=' '.join(str((edge.get('node') or {}).get('text') or '').strip() for edge in edges).strip()
        if not caption:continue
        url='https://www.instagram.com/reel/'+code
        key='feed_'+hashlib.sha256(url.encode()).hexdigest()[:32]
        published=datetime.datetime.fromtimestamp(seconds,datetime.timezone.utc).isoformat()
        video={'url':url,'title':caption[:200],'publisher':source['publisher'],'platform':'instagram',
               'published_at':published,'source':'Instagram 官方公开嵌入','relation':'来源视频'}
        cat=category(caption,source)
        items.append({'id':key,'feed_id':key,'url':url,'title':caption[:200],'summary':caption[:20000],
                      'platform':'instagram','category':cat,'category_name':CATEGORY_NAMES.get(cat,''),
                      'published_at':published,'publisher':source['publisher'],'reference_video':video,
                      'source_kind':'daily_feed','source':video['source'],'metrics':{}})
    return items


def instagram_details(item):
    code=item['url'].rsplit('/',1)[-1]
    current=reference(item['id'])
    duration=(current or {}).get('duration')
    if duration is None:
        payload=instagram_context(fetch_page(item['url']+'/embed/'))
        post=(payload.get('gql_data') or {}).get('shortcode_media') or {}
        if (payload['context'].get('copyright_blocked') or payload['context'].get('shortcode')!=code
                or post.get('shortcode')!=code or post.get('product_type')!='clips' or not post.get('is_video')
                or (post.get('owner') or {}).get('username','').lower()!=item['source_id'].split(':',1)[1]):return None
        duration=post.get('video_duration')
    if type(duration) not in (int,float) or not 3<=duration<=90:return None
    return {**item,'duration':duration,'reference_video':{**item['reference_video'],'duration':duration}}


def youtube_page_data(url):
    page=fetch_page(url).decode('utf-8')
    match=re.search(r'var ytInitialData\s*=\s*',page)
    if not match:raise ValueError('YouTube 公开页面暂时不可用')
    return json.JSONDecoder().raw_decode(page[match.end():])[0]


def youtube_series(source, existing, errors):
    """Look beyond the latest 15 uploads for the creator's public short-form series."""
    channel=source['channel_id']
    profile=source['publisher_url']
    if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',channel) or not re.fullmatch(r'https://www\.youtube\.com/@[A-Za-z0-9_.-]{1,50}',profile):
        raise ValueError('频道无效')
    shelf=youtube_page_data(profile+'/shorts')
    if (shelf.get('metadata') or {}).get('channelMetadataRenderer',{}).get('externalId')!=channel:
        raise ValueError('Shorts 公开频道不匹配')
    seen={i['url'] for i in existing}
    candidates=[]
    for node in walk(shelf.get('contents',{})):
        short=node.get('shortsLockupViewModel') or {}
        command=(short.get('onTap') or {}).get('innertubeCommand') or {}
        ident=(command.get('reelWatchEndpoint') or {}).get('videoId','')
        title=short.get('overlayMetadata',{}).get('primaryText',{}).get('content','')
        url='https://www.youtube.com/watch?v='+ident
        if (url in seen or not re.fullmatch(r'[A-Za-z0-9_-]{11}',ident)
                or not re.search(r'\binvit\w*|\breel idea\b|\bsticky notes?\b|\b(?:bookface|paper frame|optical illusion|forced perspective|infinity card|paint.wipe)\b',title,re.I)):continue
        seen.add(url)
        candidates.append((ident,title,url))
        if len(candidates)==10:break
    def detail(candidate):
        ident,title,url=candidate
        data=youtube_page_data(url)
        if data.get('currentVideoEndpoint',{}).get('watchEndpoint',{}).get('videoId')!=ident:return None
        header=next((n['videoDescriptionHeaderRenderer'] for n in walk(data.get('engagementPanels',[])) if 'videoDescriptionHeaderRenderer' in n),{})
        if header.get('channelNavigationEndpoint',{}).get('browseEndpoint',{}).get('browseId')!=channel:return None
        try:day=datetime.datetime.strptime(header['publishDate']['simpleText'],'%b %d, %Y').date()
        except (ValueError,KeyError):return None
        today=timestamp(now()).date()
        if not today-datetime.timedelta(days=MAX_AGE_DAYS)<=day<=today:return None
        caption=next((n['attributedDescription']['content'] for n in walk(data.get('contents',{}))
                      if isinstance(n.get('attributedDescription',{}).get('content'),str)),'')
        if not overseas_visuals.caption_setup(caption):return None
        published=day.isoformat()
        key='feed_'+hashlib.sha256(url.encode()).hexdigest()[:32]
        video={'url':'https://www.youtube.com/shorts/'+ident,'title':title,'publisher':source['publisher'],
               'publisher_url':source['publisher_url'],'platform':'youtube','source':'YouTube Shorts 创作者说明',
               'relation':'来源视频','thumbnail':'https://i.ytimg.com/vi/'+ident+'/hqdefault.jpg','published_at':published}
        return {'id':key,'feed_id':key,'channel_id':channel,'url':url,'title':title[:200],'summary':caption[:20000],
                'published_at':day.isoformat()+'T00:00:00+00:00','platform':'youtube','category':'','category_name':'',
                'publisher':source['publisher'],'source_kind':'daily_feed','source':video['source'],'reference_video':video,'metrics':{}}
    found=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for future in [pool.submit(detail,item) for item in candidates]:
            try:value=future.result()
            except (OSError,ValueError,KeyError):errors.add(source['publisher']);continue
            if value:found.append(value)
    return found


def parse_tiktok(blob, source):
    state=script_json(blob,'__FRONTITY_CONNECT_STATE__')
    page=state['source']['data']['/embed/@'+source['handle']]
    owner=page.get('userInfo') or {}
    if page.get('isError') or owner.get('privateAccount') or owner.get('uniqueId','').lower()!=source['handle'].lower():
        raise ValueError('TikTok公开账号不可用')
    items=[];seen=set()
    for entry in page.get('videoList',[])[:10]:
        ident=entry.get('id');caption=entry.get('desc','')
        if not isinstance(caption,str):continue
        caption=caption.strip()
        if not isinstance(ident,str) or not re.fullmatch(r'\d{15,25}',ident) or ident in seen or not caption or entry.get('privateItem'):
            continue
        if str(entry.get('authorUniqueId','')).lower()!=source['handle'].lower():continue
        height,width=entry.get('height'),entry.get('width')
        if not isinstance(height,(int,float)) or not isinstance(width,(int,float)) or width<=0 or height/width<1.3:continue
        if re.search(r'\b(unboxing|review|giveaway|interview|episode drops)\b',caption,re.I):continue
        if re.search(r'\b(no purchase necessary|official rules|sweepstakes|pre-order)\b',caption,re.I):continue
        story=bool(re.search(STORY_CUES,caption,re.I))
        brand=source['handle'] in ('scrubdaddy','liquiddeath')
        setup = overseas_visuals.caption_setup(caption)
        if not setup and re.search(r'\b(tutorial|tickets|tour dates|in theaters|in cinemas|keep your eyes peeled)\b',caption,re.I):continue
        if brand and not story and not setup and ident not in CASES:continue
        seen.add(ident)
        url='https://www.tiktok.com/@'+source['handle']+'/video/'+ident
        key='feed_'+hashlib.sha256(url.encode()).hexdigest()[:32]
        publisher=owner.get('nickname') or source['publisher']
        product_category=category(caption,source)
        video={'url':url,'title':caption,'publisher':publisher,'publisher_url':'https://www.tiktok.com/@'+source['handle'],
               'thumbnail':entry.get('coverUrl',''),'platform':'tiktok','source':'TikTok官方公开嵌入','relation':'来源视频'}
        item={'id':key,'feed_id':key,'source_id':source['source_id'],'url':url,'title':caption[:200],'summary':caption[:20000],
              'platform':'tiktok','category':product_category,'category_name':CATEGORY_NAMES.get(product_category,''),
              'source_kind':'daily_feed','source':video['source'],'publisher':publisher,'reference_video':video,'metrics':{},
              'story_candidate':story,'selection_version':SELECTION_VERSION}
        if ident in CASES:
            case=CASES[ident];item.update(title=case['title'],summary=case['summary'],category=case['category'],case_review=case)
            item['category_name']=CATEGORY_NAMES[case['category']]
        items.append(item)
    return items


def tiktok_details(item):
    current=reference(item['id'])
    if current and current.get('duration') and current.get('published_at'):
        details={key:current[key] for key in ('duration','published_at')}
    else:
        try:
            raw=script_json(fetch_page(item['url']),'__UNIVERSAL_DATA_FOR_REHYDRATION__')
            details=raw['__DEFAULT_SCOPE__']['webapp.video-detail']['itemInfo']['itemStruct']
            if details.get('id')!=item['url'].rsplit('/',1)[-1] or details.get('author',{}).get('uniqueId','').lower()!=item['url'].split('/@',1)[1].split('/')[0].lower():return None
            duration=details.get('video',{}).get('duration')
            created=datetime.datetime.fromtimestamp(int(details['createTime']),datetime.timezone.utc)
            details={'duration':duration,'published_at':created.isoformat()}
        except (KeyError,TypeError,OverflowError):return None
    stamp=timestamp(now());published=timestamp(details['published_at']);duration=details['duration']
    if type(duration) not in (int,float) or not 3<=duration<=90 or not published or not stamp-datetime.timedelta(days=MAX_AGE_DAYS)<=published<=stamp+datetime.timedelta(minutes=15):return None
    return {**item,**details,'reference_video':{**item['reference_video'],'published_at':details['published_at'],'duration':duration}}


def sources_revision():
    config=[SELECTION_VERSION,SOURCES,overseas_daily.FRONT_PAGE,overseas_daily.EDITION_SIZE,sorted((c['id'],c.get('visual_payoff','')) for c in overseas_visuals.CASES.values())]
    return hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()[:16]


def videos(urls=None):
    with db() as c:
        if urls is None:
            rows=c.execute('SELECT data FROM overseas_feed_videos ORDER BY published_at DESC LIMIT 600')
        elif urls:
            marks=','.join('?' for _ in urls)
            rows=c.execute('SELECT data FROM overseas_feed_videos WHERE url IN ('+marks+')',tuple(urls))
        else:return []
        values=[json.loads(row['data']) for row in rows]
    return [overseas_translation.enrich(value) for value in values]


def reference(ident):
    with db() as c:
        row=c.execute('SELECT data FROM overseas_feed_videos WHERE id=?',(ident,)).fetchone()
    return overseas_translation.enrich(json.loads(row['data'])) if row else None


def status():
    with db() as c:
        state=json.loads(c.execute('SELECT data FROM overseas_feed_state WHERE id=1').fetchone()[0])
        count=c.execute('SELECT count(*) FROM overseas_feed_videos').fetchone()[0]
    if state.get('state')=='running' and (timestamp(now())-timestamp(state.get('heartbeat_at') or state['last_attempt_at'])).total_seconds()>600:
        state['state']='failed'
    return {k:v for k,v in {**state,'pool_size':count,'source_count':len(SOURCES),'daily':True,'primary_platform':'tiktok',
                            'platform_counts':dict(Counter(s.get('platform','youtube') for s in SOURCES))}.items() if k not in ('run_id','heartbeat_at')}


def _claim(force):
    stamp=timestamp(now())
    zone=ZoneInfo(os.environ.get('DAOLOOK_FEED_TIMEZONE','America/New_York'))
    revision=sources_revision()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        state=json.loads(c.execute('SELECT data FROM overseas_feed_state WHERE id=1').fetchone()[0])
        attempted=timestamp(state.get('last_attempt_at'))
        elapsed=(stamp-attempted).total_seconds() if attempted else float('inf')
        heartbeat=timestamp(state.get('heartbeat_at')) or attempted
        expired=state.get('state')=='running' and (not heartbeat or (stamp-heartbeat).total_seconds()>=600)
        if state.get('state')=='running' and not expired:
            return None
        if force and elapsed<300:
            return None
        checked=timestamp(state.get('last_checked_at'))
        if not force and not expired and state.get('sources_revision')==revision and ((state.get('state')=='succeeded' and checked and checked.astimezone(zone).date()==stamp.astimezone(zone).date()) or elapsed<3600):
            return None
        token=uid()
        state.update(state='running',run_id=token,last_attempt_at=stamp.isoformat(),heartbeat_at=stamp.isoformat(),errors=[])
        c.execute('UPDATE overseas_feed_state SET data=? WHERE id=1',(dumps(state),))
        return token


def source_items(source):
    errors=set()
    try:items=parse(fetch(source),source)
    except (ValueError,OSError,KeyError):
        if not source.get('shorts_only'):raise
        items=[];errors.add(source['publisher'])
    if source.get('shorts_only'):
        try:items.extend(youtube_series(source,items,errors))
        except (ValueError,OSError,KeyError):errors.add(source['publisher'])
        if errors and not items:raise ValueError('Shorts 订阅暂时不可用')
    if source.get('platform')=='tiktok':
        # Include every caption match plus a few recent clips for the wider candidate library.
        recent=sorted(items,key=lambda i:i['url'].rsplit('/',1)[1],reverse=True)[:4]
        items=[i for i in items if i in recent or i.get('case_review') or overseas_visuals.with_setup(i).get('visual_payoff')]
    for item in items:
        item.update({k:source[k] for k in ('industry','publisher_type','source_id') if k in source})
    return items,errors


def _sync(token):
    successes=0;items=[];errors=set()
    next_heartbeat=time.monotonic()+60
    def renew():
        nonlocal next_heartbeat
        if time.monotonic()<next_heartbeat:return
        with db() as c:
            c.execute("UPDATE overseas_feed_state SET data=json_set(data,'$.heartbeat_at',?) WHERE id=1 AND json_extract(data,'$.run_id')=?",(now(),token))
        next_heartbeat=time.monotonic()+60
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(source_items,source):source for source in SOURCES}
        for future in concurrent.futures.as_completed(futures):
            renew()
            source=futures[future]
            try:
                found,issues=future.result()
                items.extend(found);errors.update(issues);successes+=1
            except Exception:
                errors.add(source['publisher'])
    details={'tiktok':tiktok_details,'instagram':instagram_details}
    missing_details=set()
    accepted=[i for i in items if i['platform'] not in details]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(details[i['platform']],i):i for i in items if i['platform'] in details}
        for future in concurrent.futures.as_completed(futures):
            renew()
            try:value=future.result()
            except Exception:
                missing_details.add(futures[future]['publisher'])
                continue
            if value:accepted.append(value)
    errors.update(missing_details)
    stamp=now();added=changed=new_matches=0
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        state=json.loads(c.execute('SELECT data FROM overseas_feed_state WHERE id=1').fetchone()[0])
        if state.get('run_id')!=token:
            return
        for item in accepted:
            current=c.execute('SELECT data,created_at FROM overseas_feed_videos WHERE id=?',(item['id'],)).fetchone()
            previous=json.loads(current['data']) if current else {}
            if previous.get('first_matched_at'):
                item['first_matched_at']=previous['first_matched_at']
            if item['url'] not in overseas_visuals.BY_URL and overseas_visuals.with_setup(item).get('visual_payoff'):
                first=previous.get('first_matched_at')
                if not first and current and overseas_visuals.with_setup(previous).get('visual_payoff'):first=current['created_at']
                item['first_matched_at']=first or stamp
                new_matches+=int(not first)
            if previous==item:
                continue
            added+=int(current is None);changed+=int(current is not None)
            c.execute('INSERT INTO overseas_feed_videos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,published_at=excluded.published_at,updated_at=excluded.updated_at',
                      (item['id'],item['url'],dumps(item),item['published_at'],stamp,stamp))
        cutoff=(timestamp(stamp)-datetime.timedelta(days=MAX_AGE_DAYS)).isoformat()
        removed=c.execute('DELETE FROM overseas_feed_videos WHERE published_at<?',(cutoff,)).rowcount
        tiktok_sources={s['source_id'] for s in SOURCES if s.get('source_id')}
        for row in c.execute('SELECT id,data FROM overseas_feed_videos').fetchall():
            data=json.loads(row['data'])
            retired=data.get('platform')=='tiktok' and (data.get('source_id') not in tiktok_sources or data.get('selection_version')!=SELECTION_VERSION)
            if successes and retired:
                removed+=c.execute('DELETE FROM overseas_feed_videos WHERE id=?',(row['id'],)).rowcount
        state.update(state='succeeded' if not errors else ('partial' if successes else 'failed'),
                     last_attempt_finished_at=stamp,added_count=added,changed_count=changed,new_match_count=new_matches,errors=sorted(errors),
                     successful_sources=successes,detail_pending_sources=sorted(missing_details),
                     removed_count=removed,sources_revision=sources_revision())
        if successes:state['last_checked_at']=stamp
        if added or changed or removed:state['last_updated_at']=stamp
        c.execute('UPDATE overseas_feed_state SET data=? WHERE id=1',(dumps(state),))
        # Preserve even an offline day's first page in the rotation history. When
        # sources recover, fill the optional page without moving the first ten.
        limit=overseas_daily.FRONT_PAGE if successes<len(SOURCES) and not new_matches else overseas_daily.EDITION_SIZE
        overseas_daily.select(c,stamp,persist=True,limit=limit)


def refresh(force=False, background=True):
    token=_claim(force)
    if token:
        if background:threading.Thread(target=_sync,args=(token,),daemon=True).start()
        else:_sync(token)
    return {**status(),'cached':token is None}


def start():
    def loop():
        event=threading.Event()
        while True:
            try:
                result=refresh(background=False)
            except Exception:
                import traceback
                traceback.print_exc()
                result={}
            event.wait(30 if result.get('state')=='running' else 1800)
    threading.Thread(target=loop,daemon=True).start()
