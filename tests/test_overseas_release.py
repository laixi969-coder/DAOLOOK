import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import overseas_daily, overseas_feed, overseas_library, overseas_release


class PublishedReviewTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.database = importlib.import_module('server.db')
        patcher = patch.object(self.database, 'DB_PATH', str(Path(folder.name) / 'db'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.database.init()

    def test_clean_install_replays_published_archives_and_rehydrates_reviewed_clips(self):
        stamp = '2026-11-26T23:00:00+00:00'
        with self.database.db() as connection:
            overseas_release.install(connection)
            overseas_release.install(connection)
            self.assertEqual(dict(connection.execute(
                'SELECT decision,count(*) FROM overseas_shot_reviews GROUP BY decision')), {'keep':15,'reject':23})
            self.assertEqual(connection.execute('SELECT count(*) FROM overseas_match_events').fetchone()[0], 17)
        with patch.object(overseas_feed, 'now', return_value=stamp):
            library = overseas_library.recommendations('', scope='selected')
        self.assertEqual(len(library), 27)
        reviewed = [card for card in library if card.get('editor_review')]
        self.assertEqual(len(reviewed), 15)
        self.assertTrue(all(card['daily_poster'].startswith('/art/overseas/') for card in reviewed))
        new = overseas_daily.edition(stamp)
        old = overseas_daily.edition(stamp, '2026-11-26.0')
        yesterday = overseas_daily.edition(stamp, '2026-11-25.0')
        previous_urls = {c['url'] for c in yesterday['items'][:10]}
        self.assertEqual(new['key'], '2026-11-26.1')
        for issue, expected in ((new, 0), (old, 8)):
            urls = {c['url'] for c in issue['items'][:10]}
            self.assertEqual(len(urls), 10)
            self.assertEqual(len(urls & previous_urls), expected)
            self.assertEqual(issue['repeated_front'], expected)
        for item in new['items'][:10]:
            self.assertTrue(item['daily_pick']['new_match'])
            self.assertTrue((Path(__file__).resolve().parents[1] / 'web' / item['daily_poster'].lstrip('/')).is_file())
            ref = overseas_daily.reference(overseas_daily.creation_reference_id(new['key'], item['url']), stamp)
            self.assertEqual((ref['url'], ref['filming']), (item['url'], item['filming']))

    def test_install_and_restart_preserve_existing_local_review_and_feed_metadata(self):
        url = 'https://www.instagram.com/p/Df-irHytxtf'
        slug = 'https://www.tiktok.com/@crocs/video/7712140494343638285'
        with self.database.db() as connection:
            connection.execute('INSERT INTO overseas_shot_reviews VALUES (?,?,?,?,NULL)',
                               (url, 'reject', '{"reason":"本地复审"}', '2026-11-27'))
            connection.execute('INSERT INTO overseas_feed_videos VALUES (?,?,?,?,?,?)',
                               ('local', slug, '{"title":"本地修订"}', '2026-11-27', '2026-11-27', '2026-11-27'))
            overseas_release.install(connection)
            self.assertEqual(connection.execute('SELECT count(*) FROM overseas_shot_reviews').fetchone()[0], 38)
            self.assertFalse(connection.execute("SELECT 1 FROM overseas_feed_videos WHERE url LIKE '%Df-irHytxtf'").fetchone())
            self.assertEqual(json.loads(connection.execute('SELECT data FROM overseas_feed_videos WHERE url=?', (slug,)).fetchone()[0])['title'], '本地修订')
            connection.execute("UPDATE overseas_shot_reviews SET decision='reject' WHERE url=?", (slug,))
            overseas_release.install(connection)
            self.assertEqual(connection.execute('SELECT decision FROM overseas_shot_reviews WHERE url=?', (slug,)).fetchone()[0], 'reject')
