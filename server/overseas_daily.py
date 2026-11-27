"""A shared daily edition of public, shootable references."""
import datetime
import hashlib
import json
import os
import re
from zoneinfo import ZoneInfo

from . import overseas_editions, overseas_visuals
from .db import db

FRONT_PAGE = 10
EDITION_SIZE = 20


def day_for(stamp):
    zone = ZoneInfo(os.environ.get('DAOLOOK_FEED_TIMEZONE', 'America/New_York'))
    return datetime.datetime.fromisoformat(stamp).astimezone(zone).date().isoformat()


def _stored(connection, day):
    return [dict(row) for row in connection.execute(
        'SELECT url,position,new_match FROM overseas_daily_picks WHERE day=? ORDER BY position', (day,))]


def front_keys(items):
    return {overseas_visuals.review_key(p['url']) for p in items[:FRONT_PAGE]}


def _previous_front(connection, day):
    yesterday = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
    issue = connection.execute('SELECT items FROM overseas_editions WHERE day=? ORDER BY issue DESC LIMIT 1',
                               (yesterday,)).fetchone()
    if issue:
        return front_keys(json.loads(issue['items']))
    picks = _stored(connection, yesterday)
    return front_keys(picks) if picks else None


def _with_overlap(edition, previous):
    front = front_keys(edition['picks'])
    return {**edition, 'repeated_front':len(front & previous) if previous is not None else None}


def _last_shown(connection, day):
    history, first_page = {}, {}
    def remember(url, shown, front):
        key = overseas_visuals.review_key(url)
        history[key] = max(shown, history.get(key, ''))
        if front:
            first_page[key] = max(front, first_page.get(key, ''))
    rows = connection.execute('SELECT url,MAX(day),MAX(CASE WHEN position<=? THEN day END) '
                              'FROM overseas_daily_picks WHERE day<? GROUP BY url', (FRONT_PAGE,day))
    for url, shown, front in rows:
        remember(url, shown, front)
    cutoff = (datetime.date.fromisoformat(day) - datetime.timedelta(days=180)).isoformat()
    snapshots = connection.execute('SELECT day,items FROM overseas_editions e WHERE day>=? AND day<? '
                                   'AND (issue>0 OR NOT EXISTS (SELECT 1 FROM overseas_daily_picks p WHERE p.day=e.day))',
                                   (cutoff, day))
    for shown, items in snapshots:
        for i, item in enumerate(json.loads(items)):
            remember(item['url'], shown, shown if i < FRONT_PAGE else None)
    return history, first_page


def select(connection, stamp, persist, limit=EDITION_SIZE):
    day = day_for(stamp)
    previous = _previous_front(connection, day)
    published = connection.execute('SELECT issue,items FROM overseas_editions WHERE day=? AND issue>0 '
                                   'ORDER BY issue DESC LIMIT 1', (day,)).fetchone()
    if published:
        edition = overseas_editions.unpack(day, published['items'], FRONT_PAGE)
        return _with_overlap({**edition, 'key': f"{day}.{published['issue']}"}, previous)
    picks = _stored(connection, day)
    if picks:
        # A source can retract a post or change its description between checks.
        marks = ','.join('?' for _ in picks)
        rows = connection.execute('SELECT url,data FROM overseas_feed_videos WHERE url IN ('+marks+')',
                                  [pick['url'] for pick in picks])
        chosen_urls = {p['url'] for p in picks}
        candidates = [case for case in overseas_visuals.CASES.values() if case['url'] in chosen_urls]
        candidates.extend(json.loads(row['data']) for row in rows)
        available = {item['url'] for item in overseas_visuals.attach_reviews(connection,candidates)
                     if overseas_visuals.with_setup(item).get('visual_payoff')}
        retained = []
        seen = set()
        for pick in picks:
            key = overseas_visuals.review_key(pick['url'])
            if pick['url'] in available and key not in seen:
                retained.append(pick)
                seen.add(key)
        if len(retained) != len(picks):
            if retained[:FRONT_PAGE] != picks[:FRONT_PAGE]:
                # Fill vacated front-page slots by ranking all eligible alternatives.
                retained = [p for p in retained if p['position'] <= FRONT_PAGE]
            picks = [dict(pick, position=position) for position,pick in enumerate(retained,1)]
            if persist:
                connection.execute('DELETE FROM overseas_daily_picks WHERE day=?', (day,))
                connection.executemany('INSERT INTO overseas_daily_picks VALUES (?,?,?,?)',
                                       [(day,p['position'],p['url'],p['new_match']) for p in picks])
    if len(picks) < (limit if persist else FRONT_PAGE):
        original_count = len(picks)
        prior_urls = previous or set()
        history, first_page = _last_shown(connection, day)
        public = list(overseas_visuals.CASES.values())
        for row in overseas_visuals.candidate_rows(connection):
            item = json.loads(row['data'])
            if overseas_visuals.review_key(item['url']) not in overseas_visuals.REVIEWED:
                public.append(item)
        pool = {}
        for item in overseas_visuals.attach_reviews(connection, public):
            item = overseas_visuals.with_setup(item)
            if item.get('visual_payoff'):
                pool.setdefault(overseas_visuals.review_key(item['url']), item)
        used = {key:set() for key in ('mechanism','publisher','industry','publisher_type')}
        def remember(item):
            for key, values in used.items():
                values.add((item.get('mechanism') or item['filming']) if key=='mechanism' else item.get(key))
        for pick in picks:
            item = pool.pop(overseas_visuals.review_key(pick['url']),None)
            if item:remember(item)
        def rank(key):
            item = pool[key]
            url = item['url']
            shown = history.get(key, '')
            matched = item.get('first_matched_at','')
            new_today = bool(matched and day_for(matched) == day)
            mechanism = item.get('mechanism') or item['filming']
            return (key in prior_urls, not new_today, bool(first_page.get(key)),
                    mechanism in used['mechanism'], item.get('publisher') in used['publisher'],
                    bool(shown), first_page.get(key,''), shown, item.get('industry') in used['industry'],
                    item.get('publisher_type') in used['publisher_type'], item.get('platform') != 'tiktok',
                    hashlib.sha256((day+url).encode()).digest())
        while pool and len(picks) < limit:
            item = pool.pop(min(pool, key=rank))
            url = item['url']
            matched = item.get('first_matched_at','')
            picks.append({'url':url, 'position':len(picks)+1, 'new_match':int(bool(matched and day_for(matched)==day))})
            remember(item)
        if persist:
            connection.executemany('INSERT INTO overseas_daily_picks(day,position,url,new_match) VALUES (?,?,?,?)',
                                   [(day, p['position'], p['url'], p['new_match']) for p in picks[original_count:]])
            cutoff = (datetime.date.fromisoformat(day) - datetime.timedelta(days=180)).isoformat()
            connection.execute('DELETE FROM overseas_daily_picks WHERE day<?', (cutoff,))
    if persist:
        overseas_editions.save_automatic(connection, day, picks)
    return _with_overlap({'day':day, 'key':f'{day}.0', 'front_page':FRONT_PAGE, 'picks':picks}, previous)


def creation_reference_id(edition_key, url):
    # Positions can change when a post is withdrawn. Bind the selection to its original URL.
    return f"edition_{edition_key}.{hashlib.sha256(url.encode()).hexdigest()[:32]}"


def reference(ident, stamp):
    match = re.fullmatch(r'edition_(\d{4}-\d{2}-\d{2})\.(0|[1-9]\d{0,8})\.[a-f0-9]{32}', ident)
    if not match:
        return None
    day, issue = match.groups()
    key = f'{day}.{issue}'
    today = day_for(stamp)
    if day > today:
        return None
    with db() as connection:
        card = None
        if day == today and issue == '0':
            # The current automatic page reads live public material, even before the first sync.
            preview = select(connection, stamp, persist=False)
            if preview['key'] == key:
                picks = [p for p in preview['picks'] if creation_reference_id(key, p['url']) == ident]
                if not picks:
                    return None
                card = next(iter(overseas_editions.cards_for_picks(connection, picks)), None)
        if card is None:
            row = connection.execute('SELECT items FROM overseas_editions WHERE day=? AND issue=?', (day, issue)).fetchone()
            items = json.loads(row['items']) if row else []
            card = next((item for item in items if creation_reference_id(key, item['url']) == ident), None)
    if card is None:
        return None
    return {**{k:v for k,v in card.items() if k not in ('daily_poster','daily_pick','landscape')},
            'source_kind':'daily_edition', 'edition_key':key}


def edition(stamp, archive_key=None):
    # Before the scheduler finishes, show a preview from the last good pool. Opening
    # the page early must not lock yesterday's cache into today's permanent edition.
    with db() as connection:
        if archive_key is not None:
            archived = overseas_editions.archive(connection, day_for(stamp), archive_key, FRONT_PAGE)
            previous = _previous_front(connection, archived['day']) if archived['day'] else None
            return _with_overlap(archived, previous)
        return select(connection, stamp, persist=False)
