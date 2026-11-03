import base64
import datetime
import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import account_deletion, adapters, maintenance, mfa
from server.app import new_user

D = importlib.import_module('server.db')


class SecurityLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / 'db')
        D.init()
        self.admin = new_user('admin@example.test', 'password123', role='admin')
        self.user = new_user('user@example.test', 'password123')

    def tearDown(self):
        D.DB_PATH = self.old_db
        self.temp.cleanup()

    def test_totp_rfc_vector_and_replay(self):
        secret = base64.b32encode(b'12345678901234567890').decode()
        with patch.dict(os.environ, {'DAOLOOK_ADMIN_TOTP_SECRET': secret}), patch('server.mfa.time.time', return_value=59):
            with D.db() as c:
                self.assertTrue(mfa.verify(c, self.admin, '287082'))
                self.assertFalse(mfa.verify(c, self.admin, '287082'))
                self.assertFalse(mfa.verify(c, self.admin, '000000'))

    def test_live_security_requires_valid_https_and_secret(self):
        secret = base64.b32encode(b'12345678901234567890').decode()
        with patch.dict(os.environ, {'DAOLOOK_ADMIN_TOTP_SECRET': secret, 'DAOLOOK_SECURE_COOKIE': '1', 'DAOLOOK_PUBLIC_ORIGIN': 'https://example.test'}, clear=True):
            mfa.validate_live_security()
            with patch.dict(os.environ, {'DAOLOOK_PUBLIC_ORIGIN': 'http://example.test'}):
                with self.assertRaises(ValueError): mfa.validate_live_security()
            with patch.dict(os.environ, {'DAOLOOK_SECURE_COOKIE': '0'}):
                with self.assertRaises(ValueError): mfa.validate_live_security()

    def test_delete_user_preserves_other_accounts_and_budget_totals(self):
        with D.db() as c:
            project = c.execute('SELECT id FROM projects WHERE user_id=?', (self.user,)).fetchone()[0]
            c.execute('INSERT INTO assets VALUES (?,?,?,?,?,?)', ('asset', project, 'name', '其他', 'private', D.now()))
            c.execute('INSERT INTO source_contents VALUES (?,?,?,?,?,?,?)', ('source', project, 'xhs', '', '{}', 1, D.now()))
            c.execute('INSERT INTO analysis_outputs VALUES (?,?,?,?,?,?)', ('analysis', 'source', '{}', '', '', D.now()))
            c.execute('INSERT INTO creation_outputs VALUES (?,?,?,?,?,?,?,?,?)', ('creation', project, 'source', 'task', '{}', '', 1, None, D.now()))
            c.execute('INSERT INTO creation_revisions VALUES (?,?,?,?,?)', ('creation', 1, '{}', 'edit', D.now()))
            c.execute('INSERT INTO generated_images VALUES (?,?,?,?,?,?)', ('image', project, 'creation', '{}', 'task', D.now()))
            c.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)', ('related', self.admin, 'task.retry', project, '{"task_ids":["task"]}', '', D.now()))
            c.execute('INSERT INTO external_calls VALUES (?,?,?,?,?,?,?,?,?,?)', ('call', self.user, None, 'test', '2026-01-01', 100, 'responded', None, None, D.now()))
            c.execute('INSERT INTO signup_grants VALUES (?,?,?)', (self.user, 12, D.now()))
        account_deletion.delete_user(self.user, self.admin)
        with D.db() as c:
            self.assertFalse(c.execute('SELECT 1 FROM users WHERE id=?', (self.user,)).fetchone())
            self.assertTrue(c.execute('SELECT 1 FROM users WHERE id=?', (self.admin,)).fetchone())
            self.assertFalse(c.execute('SELECT 1 FROM assets WHERE id=?', ('asset',)).fetchone())
            self.assertFalse(c.execute('SELECT 1 FROM creation_outputs WHERE id=?', ('creation',)).fetchone())
            self.assertFalse(c.execute('SELECT 1 FROM analysis_outputs WHERE id=?', ('analysis',)).fetchone())
            self.assertFalse(c.execute('SELECT 1 FROM audit_events WHERE id=?', ('related',)).fetchone())
            self.assertEqual(c.execute('SELECT SUM(reserved) FROM external_calls').fetchone()[0], 100)
            self.assertEqual(c.execute('SELECT SUM(amount) FROM signup_grants').fetchone()[0], 12)
            self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchone())

    def test_delete_user_rejects_frozen_credits_atomically(self):
        with D.db() as c: c.execute('UPDATE credit_accounts SET frozen=1 WHERE user_id=?', (self.user,))
        with self.assertRaises(ValueError): account_deletion.delete_user(self.user, self.admin)
        with D.db() as c: self.assertTrue(c.execute('SELECT 1 FROM users WHERE id=?', (self.user,)).fetchone())

    def test_retention_keeps_recent_and_inflight_calls(self):
        old = (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=400)).isoformat()
        with D.db() as c:
            for ident, state in [('old', 'responded'), ('active', 'started')]:
                c.execute('INSERT INTO external_calls VALUES (?,?,?,?,?,?,?,?,?,?)', (ident, self.user, None, 'test', old[:10], 1, state, None, None, old))
            c.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)', ('old', self.admin, 'old', '', '{}', '', old))
        maintenance.cleanup()
        with D.db() as c:
            self.assertEqual([r[0] for r in c.execute('SELECT id FROM external_calls')], ['active'])
            self.assertFalse(c.execute("SELECT 1 FROM audit_events WHERE id='old'").fetchone())

    def test_retention_is_bounded_and_never_purges_today_budget(self):
        old = (datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(days=400)).isoformat()
        today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        with D.db() as c:
            c.executemany('INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)',
                          [(str(i), self.admin, 'old', '', '{}', '', old) for i in range(501)])
            c.execute('INSERT INTO external_calls VALUES (?,?,?,?,?,?,?,?,?,?)', ('today', self.user, None, 'test', today, 1, 'responded', None, None, old))
        maintenance.cleanup()
        with D.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM audit_events WHERE action='old'").fetchone()[0], 1)
            self.assertTrue(c.execute("SELECT 1 FROM external_calls WHERE id='today'").fetchone())

    def test_untrusted_reference_is_bounded_and_filtered(self):
        clean = adapters.reference_for_model({'platform':'xhs', 'body':'a'*9000, 'evidence':{'password':'secret'}, 'url':'https://example.test'})
        self.assertEqual(len(clean['body']), 8000)
        self.assertNotIn('evidence', clean)
        self.assertNotIn('url', clean)

    def test_newer_database_version_is_not_opened_by_older_program(self):
        with D.db() as c:
            c.execute('PRAGMA user_version=2')
        with self.assertRaises(RuntimeError):
            D.init()
        with D.db() as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 2)
