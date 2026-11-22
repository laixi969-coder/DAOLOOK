"""Public, dated overseas playlists. Issue zero is the automatic selection."""
import hashlib
import json
from pathlib import Path

from . import overseas_translation, overseas_visuals


def save_automatic(connection, day, picks):
    if not picks:
        return
    urls = [pick['url'] for pick in picks]
    marks = ','.join('?' for _ in urls)
    rows = connection.execute('SELECT url,data FROM overseas_feed_videos WHERE url IN (' + marks + ')', urls)
    feed = {row['url']: json.loads(row['data']) for row in rows}
    items = []
    for pick in picks:
        url = pick['url']
        public = overseas_visuals.BY_URL.get(url) or feed.get(url)
        if public:
            source = overseas_translation.enrich(overseas_visuals.with_setup(public))
            card = {k: source[k] for k in ('id', 'platform', 'publisher', 'title', 'title_zh', 'summary_zh',
                    'hook_zh', 'mechanism', 'visual_payoff', 'reference_video', 'url') if k in source}
            card['idea_zh'] = overseas_translation.REVIEWED.get(source.get('summary')) or source.get('visual_payoff', '')
            card['daily_poster'] = overseas_visuals.daily_poster(source)
        else:
            # Old ranking records may outlive the feed. Preserve the actual video link.
            card = {'id': hashlib.sha256(url.encode()).hexdigest(), 'title': '往期短片', 'url': url}
        card['daily_pick'] = pick
        items.append(card)
    connection.execute('INSERT INTO overseas_editions(day,issue,items) VALUES (?,0,?) '
                       'ON CONFLICT(day,issue) DO UPDATE SET items=excluded.items',
                       (day, json.dumps(items, ensure_ascii=False)))


def install(connection):
    days = connection.execute('SELECT DISTINCT day FROM overseas_daily_picks WHERE day NOT IN '
                              '(SELECT day FROM overseas_editions WHERE issue=0)').fetchall()
    for row in days:
        picks = connection.execute('SELECT url,position,new_match FROM overseas_daily_picks '
                                   'WHERE day=? ORDER BY position', (row['day'],))
        save_automatic(connection, row['day'], [dict(pick) for pick in picks])
    folder = Path(__file__).parent / 'resources/hiccai-pop/editions'
    for path in sorted(folder.glob('*.json')):
        edition = json.loads(path.read_text())
        items = edition['items']
        for position, item in enumerate(items, 1):
            item['daily_pick'] = {'url': item['url'], 'position': position, 'new_match': False}
            item.setdefault('daily_poster', overseas_visuals.daily_poster(item))
        connection.execute('INSERT OR IGNORE INTO overseas_editions(day,issue,items) VALUES (?,?,?)',
                           (edition['day'], edition['issue'], json.dumps(items, ensure_ascii=False)))


def unpack(day, items_json, front_page):
    items = json.loads(items_json)
    return {'day': day, 'items': items, 'picks': [item['daily_pick'] for item in items], 'front_page': front_page}


def archive(connection, today, key, front_page):
    rows = connection.execute('SELECT day,issue FROM overseas_editions WHERE day<=? '
                              'ORDER BY day DESC,issue DESC', (today,)).fetchall()
    if rows and rows[0]['day'] == today:
        rows = rows[1:]  # The current issue already has its own tab.
    options = [{'day': r['day'], 'key': f"{r['day']}.{r['issue']}"} for r in rows]
    if key:
        index = next((i for i, option in enumerate(options) if option['key'] == key), None)
        if index is None:
            raise ValueError('这期推荐不存在')
    else:
        index = 0
    if rows:
        row = rows[index]
        data = connection.execute('SELECT items FROM overseas_editions WHERE day=? AND issue=?',
                                  (row['day'], row['issue'])).fetchone()
        edition = unpack(row['day'], data['items'], front_page)
        edition['key'] = options[index]['key']
    else:
        edition = unpack('', '[]', front_page)
    return {**edition, 'archive': options}
