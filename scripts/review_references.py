"""抽审公开海外候选、记录原片镜头依据或复盘近期首屏。"""
import argparse
from contextlib import closing
from datetime import date, timedelta
import hashlib
import json
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server import overseas_daily, overseas_visuals
from server.config import database_path, load_env
from server.db import now


def decisions(c):
    # Reporting on an older database should not migrate it.
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='overseas_shot_reviews'").fetchone():
        return {}
    return overseas_visuals.reviews_by_key(c)


def front_pages(c, end):
    rows = c.execute("SELECT e.day,e.items FROM overseas_editions e JOIN "
                     "(SELECT day,MAX(issue) AS issue FROM overseas_editions WHERE day<=? GROUP BY day) last "
                     "ON last.day=e.day AND last.issue=e.issue ORDER BY e.day", (end.isoformat(),))
    return {date.fromisoformat(r['day']):json.loads(r['items'])[:overseas_daily.FRONT_PAGE] for r in rows}


def report(c, end, days):
    start = end - timedelta(days=days - 1)
    pages = front_pages(c, end)
    reviews = decisions(c)
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='overseas_match_events'").fetchone():
        events = c.execute("SELECT url,matched_at FROM overseas_match_events ORDER BY matched_at")
    else:
        events = c.execute("SELECT url,json_extract(data,'$.first_matched_at') FROM overseas_feed_videos "
                           "WHERE json_extract(data,'$.first_matched_at') IS NOT NULL ORDER BY 2")
    sync = {}
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='overseas_sync_days'").fetchone():
        sync = dict(c.execute("SELECT day,coverage FROM overseas_sync_days WHERE day BETWEEN ? AND ?",
                              (start.isoformat(),end.isoformat())))
    state = c.execute("SELECT data FROM overseas_feed_state WHERE id=1").fetchone()
    last = json.loads(state[0]) if state else {}
    if last.get('state') in ('partial','succeeded','failed') and last.get('last_attempt_finished_at'):
        day = overseas_daily.day_for(last['last_attempt_finished_at'])
        level = {'succeeded':2,'partial':1,'failed':0}[last['state']]
        sync[day] = max(sync.get(day,0),level)
    counts = {}
    matched = set()
    for url, stamp in events:
        original = overseas_visuals.review_key(url)
        if original in matched:
            continue
        matched.add(original)
        day = overseas_daily.day_for(stamp)
        counts[day] = counts.get(day,0) + 1
    seen = {key for day, page in pages.items() if day < start for key in overseas_daily.front_keys(page)}
    featured = set()
    repeated = comparable = 0
    daily = []
    for i in range(days):
        day = start + timedelta(days=i)
        key = day.isoformat()
        level = sync.get(key)
        summary = {'day':key, 'sync':{2:'complete',1:'partial',0:'failed'}.get(level,'unknown'),
                   'first_matches_recorded':counts.get(key, 0 if level == 2 else None)}
        if day not in pages:
            daily.append({**summary, 'front_count':None})
            continue
        urls = overseas_daily.front_keys(pages[day])
        prev = pages.get(day - timedelta(days=1))
        repeat = len(urls & overseas_daily.front_keys(prev)) if prev is not None else None
        if repeat is not None:
            repeated += repeat
            comparable += len(urls)
        daily.append({**summary, 'front_count':len(urls), 'first_seen_in_archive':len(urls-seen),
                      'overlap_yesterday':repeat, 'overlap_rate':repeat / len(urls) if urls and prev is not None else None})
        seen.update(urls)
        featured.update(urls)
    checked = [reviews[u] for u in featured if u in reviews]
    passed = sum(r['decision'] == 'keep' for r in checked)
    return {'days':daily, 'observed_days':sum(d['front_count'] is not None for d in daily),
            'comparable_slots':comparable, 'overlap_rate':repeated / comparable if comparable else None,
            'distinct_front':len(featured), 'reviewed':len(checked), 'shootable':passed,
            'review_coverage':len(checked) / len(featured) if featured else None,
            'shootable_rate':passed / len(checked) if checked else None}


def sample(c, scope, end, days, limit, seed):
    if scope == 'front':
        start = end - timedelta(days=days-1)
        items = [i for day, page in front_pages(c, end).items() if day >= start for i in page]
    else:
        raw = [json.loads(r[0]) for r in c.execute('SELECT data FROM overseas_feed_videos ORDER BY published_at DESC LIMIT 600')]
        items = [i for i in raw if not overseas_visuals.with_setup(i).get('visual_payoff')]
    reviewed = decisions(c)
    unique = {}
    for item in items:
        original = overseas_visuals.review_key(item['url'])
        if original not in reviewed:
            unique.setdefault(original, item)
    order = sorted(unique.values(), key=lambda item: hashlib.sha256((seed+'\n'+item['url']).encode()).digest())
    return [{k:item.get(k,'') for k in ('url','title','publisher')} for item in order[:limit]]


def record(c, url, decision, details, stamp):
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='overseas_shot_reviews'").fetchone():
        raise ValueError('请先启动当前版本 Daolook 以初始化审片表')
    original = overseas_visuals.review_key(url)
    feed = next((row for row in c.execute('SELECT url, data FROM overseas_feed_videos ORDER BY created_at, url')
                 if overseas_visuals.review_key(row['url']) == original), None)
    case = overseas_visuals.REVIEWED.get(original)
    if feed:
        url = feed['url']
    elif case:
        url = case['url']
    else:
        archived = c.execute("SELECT json_extract(item.value,'$.url') FROM overseas_editions,json_each(items) item "
                             "ORDER BY day DESC,issue DESC")
        url = next((row[0] for row in archived if overseas_visuals.review_key(row[0]) == original), None)
        if not url:
            raise ValueError('仅可审片库、公开候选或归档片单中已有的原片链接')
    if decision == 'keep':
        second = details.get('second')
        if type(second) not in (float, int) or not math.isfinite(second) or second < 0 or second > 86400:
            raise ValueError('请填写镜头变化出现的有效秒数')
        duration = json.loads(feed['data']).get('duration') if feed else None
        if isinstance(duration, (int,float)) and 0 < duration < second:
            raise ValueError("镜头秒数超出原片时长")
        required = ('change','props','method','mechanism')
    elif decision == 'reject':
        required = ('reason',)
    else:
        raise ValueError('请选择 keep 或 reject')
    if any(not isinstance(details.get(k),str) or not details[k].strip() or len(details[k])>1000 for k in required):
        raise ValueError('请填写且控制在 1000 字以内：'+', '.join(required))
    selected = {key:details[key].strip() for key in required}
    first = []
    if decision == 'keep':
        title = details.get('title_zh')
        if title is not None:
            if not isinstance(title,str) or not title.strip() or len(title.strip()) > 160:
                raise ValueError('审片标题应为 1 至 160 个字')
            selected['title_zh'] = title.strip()
        selected['second'] = second
        first.append(stamp)
        # Preserve new admissions even if a future feed cleanup removes the candidate.
        if feed and not case:
            previous = next((time for link,time in c.execute('SELECT url,matched_at FROM overseas_match_events ORDER BY matched_at')
                             if overseas_visuals.review_key(link) == original), None)
            first.extend(time for time in (previous,json.loads(feed['data']).get('first_matched_at')) if time)
            if not previous:
                c.execute('INSERT INTO overseas_match_events VALUES (?,?)', (url,min(first)))
    existing = [row for row in c.execute('SELECT url,first_eligible_at FROM overseas_shot_reviews')
                if overseas_visuals.review_key(row['url']) == original]
    first.extend(row['first_eligible_at'] for row in existing if row['first_eligible_at'])
    c.executemany('DELETE FROM overseas_shot_reviews WHERE url=?', [(row['url'],) for row in existing if row['url'] != url])
    c.execute('INSERT INTO overseas_shot_reviews VALUES (?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET '
              'decision=excluded.decision,details=excluded.details,reviewed_at=excluded.reviewed_at,'
              'first_eligible_at=excluded.first_eligible_at',
              (url,decision,json.dumps(selected,ensure_ascii=False),stamp,min(first,default=None)))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--db',type=Path)
    sub = cli.add_subparsers(dest='action',required=True)
    queue = sub.add_parser('sample')
    queue.add_argument('--scope',choices=('unmatched','front'),default='unmatched')
    queue.add_argument('--limit',type=int,default=12)
    queue.add_argument('--seed',help='固定抽样顺序，默认使用结束日期')
    stats = sub.add_parser('report')
    for parser in (queue,stats):
        parser.add_argument('--days',type=int,default=14)
        parser.add_argument('--end',type=date.fromisoformat)
    write = sub.add_parser('record')
    write.add_argument('url')
    write.add_argument('decision',choices=('keep','reject'))
    write.add_argument('--second',type=float)
    write.add_argument('--title-zh',help='片库中展示的中文审片标题')
    for field in ('change','props','method','mechanism','reason'):
        write.add_argument('--'+field)
    args = cli.parse_args()
    if args.db is None:
        load_env()
        args.db = database_path()
    if args.action != 'record' and args.end is None:
        args.end = date.fromisoformat(overseas_daily.day_for(now()))
    if args.action != 'record' and not 1 <= args.days <= 366:
        cli.error('复盘天数允许 1 至 366 天')
    if args.action == 'sample' and not 1 <= args.limit <= 600:
        cli.error('一次抽审 1 至 600 条')
    mode = 'rw' if args.action=='record' else 'ro'
    try:
        with closing(sqlite3.connect(args.db.resolve().as_uri()+'?mode='+mode,uri=True,timeout=10)) as c:
            c.row_factory = sqlite3.Row
            if args.action=='record':
                with c:
                    c.execute('BEGIN IMMEDIATE')
                    record(c,args.url,args.decision,vars(args),now())
                result = {'url':args.url,'decision':args.decision}
            elif args.action=='sample':
                result = sample(c,args.scope,args.end,args.days,args.limit,args.seed or args.end.isoformat())
            else:
                result = report(c,args.end,args.days)
    except (sqlite3.Error,ValueError) as error:
        cli.error(str(error))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
