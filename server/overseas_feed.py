"""Daily public video discovery shared by projects; collections remain private."""
import concurrent.futures
import datetime
import hashlib
import json
import os
import re
import threading
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo
from .db import db, dumps, now, uid
from .adapters import NoCredentialRedirect, read_bounded

SOURCES = json.loads((Path(__file__).parent / 'resources/hiccai-pop/daily-sources.json').read_text())
NS = {'a':'http://www.w3.org/2005/Atom', 'y':'http://www.youtube.com/xml/schemas/2015', 'm':'http://search.yahoo.com/mrss/'}
MAX_AGE_DAYS = 180
CATEGORY_WORDS = {
    'A':('charger','charging','usb','iphone','phone','microphone','car mount'),
    'B':('nail','nails','mani','manis','lash','lashes','lipstick','makeup','hair','skin'),
    'C':('packing','laundry','storage','cleaning','scrubber','kitchen','air fryer','food','foods','cooking'),
    'D':('puppy','dog','cat','pet','chiot','chien','chat'),
    'E':('shirt','jacket','clothing','fashion','eyewear','glasses','bag','tote','heattech','uniqlo'),
    'F':('ferrofluid','fidget','toy','toys','magnetic field'),
    'G':('tool','tools','flashlight','camping','soldering','drill','saw'),
    'H':('screenbar','keyboard','desk','monitor','water filter','filter pitcher','lifestraw','door lock')}
CATEGORY_NAMES = {s['category']:s['category_name'] for s in SOURCES}


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
    channel=source['channel_id']
    if not re.fullmatch(r'UC[A-Za-z0-9_-]{22}',channel):
        raise ValueError('视频频道编号无效')
    # Only a fixed public YouTube endpoint is requested; no user URL or credentials.
    url='https://www.youtube.com/feeds/videos.xml?channel_id='+channel
    request=urllib.request.Request(url,headers={'User-Agent':'DAOLOOK/1.1','Accept':'application/atom+xml'})
    with urllib.request.build_opener(NoCredentialRedirect()).open(request,timeout=12) as response:
        return read_bounded(response,2*1024*1024,12)


def parse(blob, source):
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
        video={'url':url,'title':title,'publisher':publisher,'publisher_url':source['publisher_url'],
               'thumbnail':'https://i.ytimg.com/vi/'+ident+'/hqdefault.jpg','platform':'youtube',
               'source':'YouTube频道公开订阅','relation':'来源视频','published_at':published.isoformat()}
        feed_id='feed_'+hashlib.sha256(url.encode()).hexdigest()[:32]
        product_category=category(title,source)
        items.append({'id':feed_id,'feed_id':feed_id,'url':url,'title':title[:200],'summary':summary,
                      'channel_id':source['channel_id'],'platform':'youtube','category':product_category,'category_name':CATEGORY_NAMES[product_category],
                      'source_kind':'daily_feed','source':video['source'],'publisher':publisher,
                      'published_at':video['published_at'],'reference_video':video,'metrics':{}})
    return items


def videos():
    with db() as c:
        return [json.loads(row['data']) for row in c.execute('SELECT data FROM overseas_feed_videos ORDER BY published_at DESC LIMIT 600')]


def reference(ident):
    with db() as c:
        row=c.execute('SELECT data FROM overseas_feed_videos WHERE id=?',(ident,)).fetchone()
    return json.loads(row['data']) if row else None


def status():
    with db() as c:
        state=json.loads(c.execute('SELECT data FROM overseas_feed_state WHERE id=1').fetchone()[0])
        count=c.execute('SELECT count(*) FROM overseas_feed_videos').fetchone()[0]
    if state.get('state')=='running' and (timestamp(now())-timestamp(state['last_attempt_at'])).total_seconds()>600:
        state['state']='failed'
    return {k:v for k,v in {**state,'pool_size':count,'source_count':len(SOURCES),'daily':True}.items() if k!='run_id'}


def _claim(force):
    stamp=timestamp(now())
    zone=ZoneInfo(os.environ.get('DAOLOOK_FEED_TIMEZONE','America/New_York'))
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        state=json.loads(c.execute('SELECT data FROM overseas_feed_state WHERE id=1').fetchone()[0])
        attempted=timestamp(state.get('last_attempt_at'))
        elapsed=(stamp-attempted).total_seconds() if attempted else float('inf')
        if state.get('state')=='running' and elapsed<600:
            return None
        if force and elapsed<300:
            return None
        checked=timestamp(state.get('last_checked_at'))
        expired=state.get('state')=='running' and elapsed>=600
        if not force and not expired and ((state.get('state')=='succeeded' and checked and checked.astimezone(zone).date()==stamp.astimezone(zone).date()) or elapsed<3600):
            return None
        token=uid()
        state.update(state='running',run_id=token,last_attempt_at=stamp.isoformat(),errors=[])
        c.execute('UPDATE overseas_feed_state SET data=? WHERE id=1',(dumps(state),))
        return token


def _sync(token):
    successes=0;items=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(fetch,source):source for source in SOURCES}
        for future in concurrent.futures.as_completed(futures):
            source=futures[future]
            try:
                items.extend(parse(future.result(),source));successes+=1
            except Exception:
                errors.append(source['publisher'])
    stamp=now();added=changed=0
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        state=json.loads(c.execute('SELECT data FROM overseas_feed_state WHERE id=1').fetchone()[0])
        if state.get('run_id')!=token:
            return
        for item in items:
            current=c.execute('SELECT data FROM overseas_feed_videos WHERE id=?',(item['id'],)).fetchone()
            if current and json.loads(current['data'])==item:
                continue
            added+=int(current is None);changed+=int(current is not None)
            c.execute('INSERT INTO overseas_feed_videos VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,published_at=excluded.published_at,updated_at=excluded.updated_at',
                      (item['id'],item['url'],dumps(item),item['published_at'],stamp,stamp))
        cutoff=(timestamp(stamp)-datetime.timedelta(days=MAX_AGE_DAYS)).isoformat()
        removed=c.execute('DELETE FROM overseas_feed_videos WHERE published_at<?',(cutoff,)).rowcount
        channels={s['channel_id'] for s in SOURCES}
        for row in c.execute('SELECT id,data FROM overseas_feed_videos').fetchall():
            if json.loads(row['data']).get('channel_id') not in channels:
                removed+=c.execute('DELETE FROM overseas_feed_videos WHERE id=?',(row['id'],)).rowcount
        state.update(state='succeeded' if successes==len(SOURCES) else ('partial' if successes else 'failed'),
                     last_attempt_finished_at=stamp,added_count=added,changed_count=changed,errors=errors,
                     successful_sources=successes,removed_count=removed)
        if successes:state['last_checked_at']=stamp
        if added or changed or removed:state['last_updated_at']=stamp
        c.execute('UPDATE overseas_feed_state SET data=? WHERE id=1',(dumps(state),))


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
