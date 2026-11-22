"""A shared daily edition of public, shootable references."""
import datetime
import hashlib
import json
import os
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


def select(connection, stamp, persist, limit=EDITION_SIZE):
    day = day_for(stamp)
    published = connection.execute('SELECT items FROM overseas_editions WHERE day=? AND issue>0 '
                                   'ORDER BY issue DESC LIMIT 1', (day,)).fetchone()
    if published:
        return overseas_editions.unpack(day, published['items'], FRONT_PAGE)
    picks = _stored(connection, day)
    if picks:
        # A source can retract a post or change its description between checks.
        marks = ','.join('?' for _ in picks)
        rows = connection.execute('SELECT url,data FROM overseas_feed_videos WHERE url IN ('+marks+')',
                                  [pick['url'] for pick in picks])
        available = {url for url,case in overseas_visuals.BY_URL.items() if case.get('visual_payoff')}
        available.update(row['url'] for row in rows if overseas_visuals.with_setup(json.loads(row['data'])).get('visual_payoff'))
        retained = [pick for pick in picks if pick['url'] in available]
        if len(retained) != len(picks):
            if any(p['position'] <= FRONT_PAGE and p['url'] not in available for p in picks):
                # Fill vacated front-page slots by ranking all eligible alternatives.
                retained = [p for p in retained if p['position'] <= FRONT_PAGE]
            picks = [dict(pick, position=position) for position,pick in enumerate(retained,1)]
            if persist:
                connection.execute('DELETE FROM overseas_daily_picks WHERE day=?', (day,))
                connection.executemany('INSERT INTO overseas_daily_picks VALUES (?,?,?,?)',
                                       [(day,p['position'],p['url'],p['new_match']) for p in picks])
    if len(picks) < (limit if persist else FRONT_PAGE):
        original_count = len(picks)
        yesterday = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
        history = dict(connection.execute('SELECT url,max(day) FROM overseas_daily_picks WHERE day<? GROUP BY url', (day,)))
        first_page = dict(connection.execute('SELECT url,max(day) FROM overseas_daily_picks WHERE day<? AND position<=? GROUP BY url', (day,FRONT_PAGE)))
        pool = {case['url']: case for case in overseas_visuals.CASES.values() if case.get('visual_payoff')}
        for row in connection.execute('SELECT data FROM overseas_feed_videos ORDER BY published_at DESC LIMIT 600'):
            item = overseas_visuals.with_setup(json.loads(row['data']))
            if item.get('visual_payoff') and overseas_visuals.review_key(item['url']) not in overseas_visuals.REVIEWED:
                pool[item['url']] = item
        used = {key:set() for key in ('mechanism','publisher','industry','publisher_type')}
        def remember(item):
            for key, values in used.items():
                values.add((item.get('mechanism') or item['filming']) if key=='mechanism' else item.get(key))
        for pick in picks:
            item = pool.pop(pick['url'],None)
            if item:remember(item)
        def rank(item):
            url = item['url']
            shown = history.get(url, '')
            matched = item.get('first_matched_at','')
            new_today = bool(matched and day_for(matched) == day)
            mechanism = item.get('mechanism') or item['filming']
            return (first_page.get(url)==yesterday, mechanism in used['mechanism'], item.get('publisher') in used['publisher'],
                    bool(shown), shown, first_page.get(url,''), not new_today, item.get('industry') in used['industry'],
                    item.get('publisher_type') in used['publisher_type'], item.get('platform') != 'tiktok',
                    hashlib.sha256((day+url).encode()).digest())
        while pool and len(picks) < limit:
            item = min(pool.values(), key=rank)
            url = item['url']
            matched = item.get('first_matched_at','')
            picks.append({'url':url, 'position':len(picks)+1, 'new_match':int(bool(matched and day_for(matched)==day))})
            remember(item)
            del pool[url]
        if persist:
            connection.executemany('INSERT INTO overseas_daily_picks(day,position,url,new_match) VALUES (?,?,?,?)',
                                   [(day, p['position'], p['url'], p['new_match']) for p in picks[original_count:]])
            cutoff = (datetime.date.fromisoformat(day) - datetime.timedelta(days=180)).isoformat()
            connection.execute('DELETE FROM overseas_daily_picks WHERE day<?', (cutoff,))
    if persist:
        overseas_editions.save_automatic(connection, day, picks)
    return {'day':day, 'front_page':FRONT_PAGE, 'picks':picks}


def edition(stamp, archive_key=None):
    # Before the scheduler finishes, show a preview from the last good pool. Opening
    # the page early must not lock yesterday's cache into today's permanent edition.
    with db() as connection:
        if archive_key is not None:
            return overseas_editions.archive(connection, day_for(stamp), archive_key, FRONT_PAGE)
        return select(connection, stamp, persist=False)
