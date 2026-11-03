import datetime
import os
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from zoneinfo import ZoneInfo

from server import workspace


class FixedDateTime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 1, 2, 0, 30, tzinfo=ZoneInfo('Asia/Shanghai')).astimezone(tz)


class WorkspaceTimezoneTests(unittest.TestCase):
    def test_today_uses_configured_zone_instead_of_server_zone(self):
        rows = [dict(platform='xhs', data='{}', created_at='2026-01-01T16:15:00+00:00', status=None, result=None)]
        class Connection:
            def execute(self, *args):
                return self
            def fetchall(self):
                return rows
        @contextmanager
        def fake_db():
            yield Connection()
        with patch.object(workspace, 'db', fake_db), patch.object(workspace.datetime, 'datetime', FixedDateTime):
            with patch.dict(os.environ, {'DAOLOOK_DISPLAY_TIMEZONE': 'Asia/Shanghai'}):
                self.assertEqual(workspace.stats('project')['today'], 1)
            with patch.dict(os.environ, {'DAOLOOK_DISPLAY_TIMEZONE': 'UTC'}):
                self.assertEqual(workspace.stats('project')['today'], 1)
            rows[0]['created_at'] = '2026-01-01T15:15:00+00:00'
            with patch.dict(os.environ, {'DAOLOOK_DISPLAY_TIMEZONE': 'Asia/Shanghai'}):
                self.assertEqual(workspace.stats('project')['today'], 0)
            with patch.dict(os.environ, {'DAOLOOK_DISPLAY_TIMEZONE': 'UTC'}):
                self.assertEqual(workspace.stats('project')['today'], 1)
