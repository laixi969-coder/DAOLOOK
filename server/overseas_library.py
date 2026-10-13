"""Project-scoped creative collection; unknown metrics stay unknown."""
import copy
import datetime
import json
import re
import urllib.parse
from pathlib import Path
from .db import db, dumps, uid, now, setting
from .discovery import parse_count
from . import overseas_feed, overseas_translation

PLATFORMS = {'tiktok': 'TikTok', 'instagram': 'Instagram Reels', 'youtube': 'YouTube Shorts'}
ARCHETYPES = json.loads((Path(__file__).parent / 'resources/viral-shorts-agent/archetypes.json').read_text())
REFERENCE_VIDEOS = {v['archetype_id']:v for v in json.loads((Path(__file__).parent / 'resources/hiccai-pop/reference-videos.json').read_text())}
CATEGORIES = {a['category']: a['category_name'] for a in ARCHETYPES}
ALIASES = {'A':'tech charger charging phone car 数码 充电 手机 汽车', 'B':'beauty skin makeup 美妆 护肤', 'C':'home kitchen cleaning storage coffee 家居 厨房 清洁 收纳 咖啡', 'D':'pet baby dog cat 宠物 母婴 猫 狗', 'E':'fashion clothing shoes 服饰 鞋 包', 'F':'toy light asmr 玩具 解压 灯', 'G':'outdoor tools camping 户外 工具 露营', 'H':'safety desk keyboard 独居 安全 桌面 键盘'}
KEYWORDS = {'charger':'充电','charging':'充电','wireless':'无线','foldable':'折叠','phone':'手机','car':'车','beauty':'美妆','makeup':'妆','skin':'皮肤','cleaning':'清洁','storage':'收纳','coffee':'咖啡','kitchen':'厨房','dog':'狗','cat':'猫','baby':'儿童','pet':'宠物','shoes':'鞋','clothing':'衣','toy':'玩具','camping':'露营','keyboard':'键盘'}


def text(value, label, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f'{label}须为最多{limit}字的文本')
    return value.strip()


def canonical_url(value):
    value = text(value, '参考链接', 2000, True)
    u = urllib.parse.urlsplit(value)
    if u.scheme != 'https' or u.username or u.password or u.port not in (None,443):
        raise ValueError('请提供HTTPS社媒内容链接')
    host = (u.hostname or '').lower()
    p = next((p for p, domains in {'tiktok':('tiktok.com',),'instagram':('instagram.com',),'youtube':('youtube.com','youtu.be')}.items()
              if any(host == d or host.endswith('.'+d) for d in domains)), None)
    if not p:
        raise ValueError('仅支持TikTok、Instagram和YouTube内容链接')
    path = u.path.rstrip('/')
    if p == 'youtube':
        video = path.lstrip('/') if host == 'youtu.be' else (path.split('/')[-1] if path.startswith('/shorts/') else urllib.parse.parse_qs(u.query).get('v',[''])[0])
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video):
            raise ValueError('请提供YouTube视频或Shorts链接')
        return p, 'https://www.youtube.com/watch?v='+video
    if p == 'instagram' and not re.fullmatch(r'/(?:reel|reels|p)/[A-Za-z0-9_-]+',path):
        raise ValueError('请提供Instagram Reel或帖子的链接')
    if p == 'tiktok' and not (re.fullmatch(r'/@[^/]+/video/\d+',path) or (host in ('vm.tiktok.com','vt.tiktok.com') and re.fullmatch(r'/[A-Za-z0-9]+',path)) or path.startswith('/t/')):
        raise ValueError('请提供TikTok视频或分享链接')
    return p, urllib.parse.urlunsplit(('https',host,path,'',''))


def with_reference_video(value):
    ident=value.get('archetype_id') or value.get('id')
    video=REFERENCE_VIDEOS.get(ident)
    if not video and value.get('feed_id'):
        current=overseas_feed.reference(value['feed_id'])
        if current and current.get('url')==value.get('url'):video=current.get('reference_video')
    value={**value,'reference_video':copy.deepcopy(video)} if video else value
    return overseas_translation.enrich(value)


def view(row):
    return with_reference_video({**json.loads(row['data']), 'id':row['id'], 'saved':bool(row['saved']), 'collected_at':row['created_at'], 'updated_at':row['updated_at']})


def list_ideas(project):
    with db() as c:
        return [view(r) for r in c.execute('SELECT * FROM overseas_ideas WHERE project_id=? AND deleted_at IS NULL ORDER BY updated_at DESC',(project,))]


def reference(project, ident):
    if ident.startswith('feed_'):
        return overseas_feed.reference(ident)
    if ident.startswith('archetype_'):
        value=next((a for a in ARCHETYPES if a['id']==ident), None)
        return with_reference_video(copy.deepcopy(value)) if value else None
    with db() as c:
        row = c.execute('SELECT * FROM overseas_ideas WHERE id=? AND project_id=? AND deleted_at IS NULL',(ident,project)).fetchone()
        return view(row) if row else None


def store(project, value, saved=False):
    key = value.get('archetype_id') or value['url']
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT * FROM overseas_ideas WHERE project_id=? AND source_key=?',(project,key)).fetchone()
        if row:
            # Search refresh does not erase the user's collection status.
            merged = {**json.loads(row['data']), **value}
            c.execute('UPDATE overseas_ideas SET data=?,saved=?,deleted_at=NULL,updated_at=? WHERE id=?',(dumps(merged),int(saved or row['saved']),now(),row['id']))
            ident=row['id']
        else:
            ident=uid(); timestamp=now()
            c.execute('INSERT INTO overseas_ideas VALUES (?,?,?,?,?,NULL,?,?)',(ident,project,key,dumps(value),int(saved),timestamp,timestamp))
        return view(c.execute('SELECT * FROM overseas_ideas WHERE id=?',(ident,)).fetchone())


def collect(project, data):
    if data.get('feed_id'):
        ident=text(data['feed_id'],'推荐编号',80,True)
        value=overseas_feed.reference(ident)
        if not value:raise ValueError('推荐创意不存在')
        value.pop('id')
    elif data.get('archetype_id'):
        ident=text(data['archetype_id'],'原型号',40,True)
        value=reference(project,ident)
        if not value: raise ValueError('创意原型不存在')
        value['archetype_id']=value.pop('id')
    else:
        p,url=canonical_url(data.get('url'))
        category=text(data.get('category',''),'品类',1)
        if category and category not in CATEGORIES: raise ValueError('品类无效')
        value={'platform':p,'url':url,'title':text(data.get('title'),'标题',200,True),
               'summary':text(data.get('summary',''),'创意说明/字幕',20000),
               'category':category,'category_name':CATEGORIES.get(category,'待分类'),
               'mechanism':text(data.get('mechanism',''),'借鉴点',2000),
               'source_kind':'manual','source':'用户手动收集','metrics':{},
               'note':'链接与说明由用户录入；未自动读取视频画面或验证表现。'}
    return store(project,value,True)


def recommendations(project, query='', category='', saved=False, platform='all'):
    if category and category not in CATEGORIES: raise ValueError('品类无效')
    if platform not in (*PLATFORMS,'all'): raise ValueError('平台无效')
    records=list_ideas(project)
    existing={r.get('archetype_id'):r for r in records if r.get('archetype_id')}
    by_url={r.get('url'):r for r in records if r.get('url')}
    fresh=[by_url.get(item['url'],{**item,'saved':False}) for item in overseas_feed.videos()] if not saved else []
    items=records if saved else fresh+[r for r in records if not r.get('archetype_id')] + [existing.get(a['id'],{**with_reference_video(a),'saved':False}) for a in ARCHETYPES]
    tokens=[t for t in re.split(r'\s+',query.lower()) if t]
    scored=[];seen=set()
    for i,item in enumerate(items):
        link=(item.get('reference_video') or {}).get('url') or item.get('url') or item['id']
        if link in seen:continue
        if saved and not item['saved']: continue
        if category and item.get('category') not in (category,''): continue
        actual_platform=(item.get('reference_video') or {}).get('platform') or item.get('platform')
        if platform!='all' and actual_platform!=platform: continue
        corpus=' '.join(str(item.get(k,'')) for k in ('title','summary','title_zh','summary_zh','category_name','mechanism','reflex','technique')).lower()
        corpus+=' '+str((item.get('reference_video') or {}).get('title_zh','')).lower()
        direct=[t for t in tokens if t in corpus or (KEYWORDS.get(t) and KEYWORDS[t] in corpus)]
        hits=[t for t in tokens if t in corpus or t in ALIASES.get(item.get('category'),'') or t in direct]
        if tokens and not hits: continue
        seen.add(link)
        reason='匹配关键词：'+'、'.join(direct) if direct else ('同类创意：'+item.get('category_name','') if hits else ('匹配所选品类' if category else '可复用的创意结构，按资料顺序展示'))
        value={**item,'recommendation':reason}
        published=overseas_feed.timestamp(item.get('published_at') or item.get('collected_at'))
        kind=0 if item.get('source_kind')=='daily_feed' else (2 if item.get('source_kind')=='archetype' else 1)
        reviewed=0 if item.get('case_review') else 1
        platform_rank=0 if actual_platform=='tiktok' else 1
        story_rank=0 if item.get('story_candidate') else 1
        scored.append((-(4*len(direct)+len(hits)),reviewed,platform_rank,story_rank,kind,-published.timestamp() if published else 0,i,value))
    return [value for *_,value in sorted(scored)][:120]


def normalize(raw,p):
    from .adapters import walk
    results=[]; seen=set()
    for node in walk(raw):
        node=node.get('media') if isinstance(node.get('media'),dict) else node
        title=node.get('desc') or node.get('title') or node.get('caption')
        if isinstance(title,dict): title=title.get('text') or title.get('simpleText') or ''.join(r.get('text','') for r in title.get('runs',[]) if isinstance(r,dict))
        url=node.get('share_url') or node.get('url') or ''
        if p=='tiktok' and node.get('id') and isinstance(node.get('author'),dict):
            author=node['author'].get('uniqueId') or node['author'].get('unique_id')
            if author and str(node['id']).isdigit(): url=f"https://www.tiktok.com/@{author}/video/{node['id']}"
        if p=='instagram' and node.get('code'):
            url='https://www.instagram.com/reel/'+node['code']+'/'
        if p=='youtube' and (node.get('video_id') or node.get('videoId')):
            url='https://www.youtube.com/watch?v='+str(node.get('video_id') or node.get('videoId'))
        try: detected,url=canonical_url(url)
        except (ValueError,TypeError): continue
        if detected!=p or url in seen or not title: continue
        seen.add(url)
        stats=node.get('stats') or node.get('statistics') or node
        if not isinstance(stats,dict): stats={}
        metrics={}
        for name,keys in {'views':('playCount','play_count','view_count','views'),'likes':('diggCount','like_count','likeCount'),'comments':('commentCount','comment_count'),'shares':('shareCount','share_count')}.items():
            value=next((parse_count(stats.get(k)) for k in keys if k in stats),None)
            if value is not None: metrics[name]=value
        results.append({'platform':p,'url':url,'title':str(title)[:200],'summary':str(title)[:20000],
                        'source_kind':'data_source','source':'TikHub公开搜索','metrics':metrics,'category':'','category_name':'待分类',
                        'fetched_at':now(),'note':'搜索候选，非平台推荐；尚未验证是否爆款。未读取完整画面。'})
        if len(results)==20: break
    return results


def search(project,p,query):
    from .adapters import TikHubAdapter
    if p not in PLATFORMS: raise ValueError('请选择海外平台')
    query=text(query,'搜索词',100,True)
    if setting('mode')=='demo' or not setting('tikhub').get('api_key'):
        raise ValueError('当前未启用海外实时数据源，可先浏览内置原型或手动收集链接；管理员配置TikHub并启用真实服务后可搜索。')
    with db() as c:
        cached=c.execute('SELECT * FROM overseas_searches WHERE project_id=? AND platform=? AND query=?',(project,p,query)).fetchone()
    if cached and datetime.datetime.fromisoformat(cached['updated_at']) > datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(minutes=15):
        values=[reference(project,i) for i in json.loads(cached['ids'])]
        return {'items':[v for v in values if v], 'cached':True,'fetched_at':cached['updated_at']}
    values=normalize(TikHubAdapter().call(p,'search',query+' #shorts' if p=='youtube' else query),p)
    if not values: raise ValueError('数据源未返回可识别的视频候选，请检查接口响应；可继续手动收集链接。')
    items=[store(project,{**v,'query':query}) for v in values]
    with db() as c:
        c.execute('INSERT OR REPLACE INTO overseas_searches VALUES (?,?,?,?,?)',(project,p,query,dumps([v['id'] for v in items]),now()))
    return {'items':items,'cached':False,'fetched_at':items[0]['fetched_at']}
