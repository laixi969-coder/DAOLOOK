"""Isolated regressions for approval provenance and real transport budgets."""
import importlib
import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from server import access, adapters, spending

database = importlib.import_module('server.db')


class AccessBudgetReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='daolook-access-review-')
        self.previous_path = database.DB_PATH
        database.DB_PATH = self.temporary.name + '/db.sqlite'
        self.environment = patch.dict(os.environ, {
            'DAOLOOK_MODE': 'demo',
            'DAOLOOK_EXTERNAL_PRICES': json.dumps({'tikhub': {'per_call': 3}}),
            'DAOLOOK_DAILY_BUDGET_MICROUSD': '100',
            'DAOLOOK_USER_DAILY_BUDGET_MICROUSD': '100',
        })
        self.environment.start()
        database.init()
        with database.db() as c:
            access.initialize(c)

    def tearDown(self):
        self.environment.stop()
        database.DB_PATH = self.previous_path
        self.temporary.cleanup()

    def account(self, role='user', demo=False, verified=False, balance=100):
        user = database.uid()
        with database.db() as c:
            c.execute('INSERT INTO users VALUES (?,?,?,?,?)',
                      (user, user + '@review.test', None, role, database.now()))
            c.execute('INSERT INTO credit_accounts VALUES (?,?,0)', (user, balance))
            access.create(c, user, demo=demo, verified=verified, role=role)
        return user

    def test_legacy_initialization_only_approves_admins(self):
        user = self.account()
        admin = self.account(role='admin')
        with database.db() as c:
            c.execute('DELETE FROM live_accounts')
            access.initialize(c)
            access.initialize(c)
            access.require_live(c, admin)
            with self.assertRaises(ValueError):
                access.require_live(c, user)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM live_accounts').fetchone()[0], 1)

    def test_demo_mode_transition_cannot_enable_paid_transport_or_approval(self):
        demo = self.account(demo=True, balance=300)
        admin = self.account(role='admin')
        with database.db() as c:
            c.execute("UPDATE settings SET value=? WHERE key='mode'", (database.dumps('live'),))
            with self.assertRaises(ValueError):
                access.approve(c, demo, admin, 'admin_approval', preserve_balance=True)
        with spending.scope(demo), patch.object(adapters, 'public_opener') as opener:
            with self.assertRaises(spending.BudgetExceeded):
                adapters.request_json('https://example.com/api', billing='tikhub')
            opener.assert_not_called()

    def test_historical_generated_demo_accounts_remain_ineligible(self):
        user = self.account()
        admin = self.account(role='admin')
        with database.db() as c:
            c.execute('UPDATE users SET email=? WHERE id=?', ('demo-123456789abc@daolook.local', user))
            access.initialize(c)
            with self.assertRaises(ValueError):
                access.approve(c, user, admin, 'admin_approval', preserve_balance=True)
            with self.assertRaises(ValueError):
                access.require_live(c, user)

    def test_verified_creation_preserves_budgeted_welcome(self):
        user = self.account(verified=True)
        with database.db() as c:
            access.require_live(c, user)
            self.assertEqual(c.execute('SELECT balance FROM credit_accounts WHERE user_id=?', (user,)).fetchone()[0], 100)

    def test_legacy_mailbox_activation_resets_wallet_once_and_is_audited(self):
        user = self.account(balance=300)
        with database.db() as c:
            c.execute('BEGIN IMMEDIATE')
            self.assertTrue(access.approve(c, user, user, 'mailbox_verified'))
            c.execute('UPDATE credit_accounts SET balance=25 WHERE user_id=?', (user,))
            self.assertFalse(access.approve(c, user, user, 'mailbox_verified'))
            self.assertEqual(c.execute('SELECT balance FROM credit_accounts WHERE user_id=?', (user,)).fetchone()[0], 25)
            self.assertEqual(c.execute("SELECT SUM(amount) FROM credit_ledger WHERE user_id=? AND kind='DEDUCT'", (user,)).fetchone()[0], -300)
            records = c.execute("SELECT actor_id,details FROM audit_events WHERE action='account.live_approved'").fetchall()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['actor_id'], user)
            self.assertEqual(json.loads(records[0]['details'])['balance'], 0)

    def test_only_explicit_admin_approval_preserves_legacy_balance(self):
        user = self.account()
        other = self.account()
        admin = self.account(role='admin')
        with database.db() as c:
            with self.assertRaises(ValueError):
                access.approve(c, user, user, 'mailbox_verified', preserve_balance=True)
            with self.assertRaises(ValueError):
                access.approve(c, user, other, 'mailbox_verified')
            self.assertTrue(access.approve(c, user, admin, 'admin_approval', preserve_balance=True))
            self.assertEqual(c.execute('SELECT balance FROM credit_accounts WHERE user_id=?', (user,)).fetchone()[0], 100)
            details=json.loads(c.execute("SELECT details FROM audit_events WHERE target=?", (user,)).fetchone()[0])
            self.assertTrue(details['preserve_balance'])

    def test_activation_refuses_frozen_or_active_work(self):
        user = self.account()
        with database.db() as c:
            c.execute('UPDATE credit_accounts SET frozen=1 WHERE user_id=?', (user,))
            with self.assertRaises(ValueError):
                access.approve(c, user, user, 'mailbox_verified')
            c.execute('UPDATE credit_accounts SET frozen=0 WHERE user_id=?', (user,))
            c.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (database.uid(),user,None,'search','PENDING','{}',None,None,0,None,None,database.now(),database.now()))
            with self.assertRaises(ValueError):
                access.approve(c, user, user, 'mailbox_verified')
            self.assertIsNone(c.execute('SELECT 1 FROM live_accounts WHERE user_id=?', (user,)).fetchone())

    def test_real_admin_transport_in_demo_mode_is_metered_and_fail_closed(self):
        admin = self.account(role='admin')
        with spending.scope(admin), patch.object(adapters, 'public_opener') as opener:
            opener.return_value.open.return_value = io.BytesIO(b'{}')
            adapters.request_json('https://example.com/api', billing='tikhub')
            self.assertEqual(opener.return_value.open.call_count, 1)
        with database.db() as c:
            self.assertEqual(tuple(c.execute('SELECT reserved,state FROM external_calls').fetchone()), (3, 'responded'))
        with patch.dict(os.environ, {'DAOLOOK_EXTERNAL_PRICES': '{}'}), spending.scope(admin), patch.object(adapters, 'public_opener') as opener:
            with self.assertRaises(spending.BudgetExceeded):
                adapters.request_json('https://example.com/api', billing='tikhub')
            opener.assert_not_called()

    def test_demo_task_scope_refuses_real_transport_even_for_admin(self):
        admin = self.account(role='admin')
        with spending.scope(admin, paid=False), patch.object(adapters, 'public_opener') as opener:
            with self.assertRaises(spending.BudgetExceeded):
                adapters.request_json('https://example.com/api', billing='tikhub')
            opener.assert_not_called()

    def test_concurrent_global_and_personal_caps_cannot_be_overdrawn(self):
        users = [self.account(verified=True) for _ in range(3)]
        def reserve(index):
            with spending.scope(users[index % len(users)]):
                try:
                    return spending.reserve('tikhub', None)
                except spending.BudgetExceeded:
                    return None
        with patch.dict(os.environ, {'DAOLOOK_DAILY_BUDGET_MICROUSD': '7'}):
            with ThreadPoolExecutor(max_workers=6) as pool:
                self.assertEqual(sum(bool(result) for result in pool.map(reserve, range(12))), 2)
        with database.db() as c:
            c.execute('DELETE FROM external_calls')
        with patch.dict(os.environ, {'DAOLOOK_USER_DAILY_BUDGET_MICROUSD': '4'}):
            with spending.scope(users[0]):
                spending.reserve('tikhub', None)
                with self.assertRaises(spending.BudgetExceeded):
                    spending.reserve('tikhub', None)

    def test_malformed_usage_cannot_release_budget_or_break_finalization(self):
        user = self.account(verified=True)
        with spending.scope(user):
            for usage in (None, [], 'invalid', {'prompt_tokens': True, 'completion_tokens': 2**80}):
                ident = spending.reserve('tikhub', None)
                spending.finish(ident, {'usage': usage})
        with database.db() as c:
            self.assertEqual(c.execute('SELECT SUM(reserved) FROM external_calls').fetchone()[0], 12)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM external_calls WHERE state='responded' AND input_tokens IS NULL AND output_tokens IS NULL").fetchone()[0], 4)

    def test_invalid_output_bounds_or_budget_configuration_stop_transport(self):
        admin = self.account(role='admin')
        prices = {'model:default/review': {'input_per_million': 1000000, 'output_per_million': 1000000}}
        with patch.dict(os.environ, {'DAOLOOK_EXTERNAL_PRICES': json.dumps(prices)}), spending.scope(admin):
            for maximum in (0, -1, True, 8193, '8192'):
                with self.assertRaises(spending.BudgetExceeded):
                    spending.reserve('model:default/review', {'messages': [], 'max_tokens': maximum})
        with patch.dict(os.environ, {'DAOLOOK_DAILY_BUDGET_MICROUSD': '-1'}), spending.scope(admin):
            with self.assertRaises(spending.BudgetExceeded):
                spending.reserve('tikhub', None)
