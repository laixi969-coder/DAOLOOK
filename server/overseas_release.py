"""Install published editorial decisions and their public sources on application startup."""
import json
from pathlib import Path

from . import overseas_visuals


def install(connection):
    folder = Path(__file__).parent / 'resources/hiccai-pop'
    for path in sorted(folder.glob('reviews-*.json')):
        key = 'overseas_release_' + path.stem
        if connection.execute('SELECT 1 FROM settings WHERE key=?', (key,)).fetchone():
            continue
        release = json.loads(path.read_text(encoding='utf-8'))
        stamp = release['reviewed_at']
        # A locally reviewed alias belongs to the same film. Keep the local decision.
        local = overseas_visuals.reviews_by_key(connection)
        for item in release['reviews']:
            if overseas_visuals.review_key(item['url']) in local:
                continue
            first = stamp if item['decision'] == 'keep' else None
            connection.execute('INSERT INTO overseas_shot_reviews VALUES (?,?,?,?,?)',
                               (item['url'], item['decision'], json.dumps(item['details'], ensure_ascii=False), stamp, first))
        for video in release['videos']:
            url = video['url']
            previous = local.get(overseas_visuals.review_key(url))
            if previous is not None and previous['decision'] == 'reject':
                continue
            connection.execute('INSERT INTO overseas_feed_videos VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING',
                               (video['id'], url, json.dumps(video, ensure_ascii=False), video['published_at'], stamp, stamp))
            first = video.get('first_matched_at') or (previous and previous['first_eligible_at']) or stamp
            connection.execute('INSERT OR IGNORE INTO overseas_match_events VALUES (?,?)',
                               (previous['url'] if previous is not None else url, first))
        connection.execute('INSERT INTO settings VALUES (?,?)', (key, '1'))
