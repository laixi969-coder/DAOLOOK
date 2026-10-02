"""Isolated adversarial regressions: no real providers, no production database."""
import importlib
import io
import json
import queue
import socket
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch, MagicMock

from server import jobs, adapters, maintenance
from server.app import new_user

D = importlib.import_module('server.db')


class AdversarialTasks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = D.DB_PATH
        D.DB_PATH = str(Path(self.temp.name) / 'test.sqlite')
        D.init()
        self.user = new_user('redteam@local.test', demo=True)
        with D.db() as c:
            self.project = c.execute('SELECT id FROM projects WHERE user_id=?', (self.user,)).fetchone()[0]
            self.source = c.execute('SELECT id FROM source_contents WHERE project_id=?', (self.project,)).fetchone()[0]
        self.queue_patch = patch.object(jobs.Q, 'put')
        self.queue_patch.start()

    def tearDown(self):
        self.queue_patch.stop()
        D.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_double_click_freezes_only_once_under_concurrency(self):
        def submit(_):
            try:
                return jobs.submit(self.user, self.project, 'create', {'source_id': self.source})
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            accepted = list(pool.map(submit, range(2)))
        self.assertEqual(sum(bool(x) for x in accepted), 1)
        with D.db() as c:
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts').fetchone()), (285, 15))

    def test_user_queue_cap_is_atomic_even_for_zero_cost_tasks(self):
        with D.db() as c:
            rules = D.setting('rules')
            rules['create'] = 0
            c.execute("UPDATE settings SET value=? WHERE key='rules'", (D.dumps(rules),))
        with patch.object(jobs, 'MAX_USER_ACTIVE', 2, create=True):
            jobs.submit(self.user, self.project, 'create', {'requirements': 'one'})
            jobs.submit(self.user, self.project, 'create', {'requirements': 'two'})
            with self.assertRaisesRegex(ValueError, '进行中|排队'):
                jobs.submit_many(self.user, self.project, 'create', [{'requirements': 'three'}, {'requirements': 'four'}])
        with D.db() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0], 2)

    def test_cancel_during_fetch_stops_before_model_generation(self):
        payload = {'source_id': D.uid(), 'brief': {'platform': 'xhs', 'topic': '咖啡', 'goal': 'leads'}, 'temporary': '真实资料'}
        ident = jobs.submit(self.user, self.project, 'original', payload)
        def fetched(*args):
            jobs.cancel(ident, self.user)
            return []
        with patch.object(adapters, 'fetch_benchmark', side_effect=fetched), patch.object(adapters, 'create_original', return_value=([], 'test')) as create:
            jobs.run(ident)
        create.assert_not_called()

    def test_global_queue_cap_does_not_freeze_more_credits(self):
        with patch.object(jobs, 'MAX_GLOBAL_ACTIVE', 1):
            jobs.submit(self.user, self.project, 'create', {'requirements': 'one'})
            with self.assertRaisesRegex(ValueError, '排队'):
                jobs.submit(self.user, self.project, 'create', {'requirements': 'two'})
        with D.db() as c:
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts').fetchone()), (285, 15))

    def test_memory_queue_full_rolls_back_entire_batch(self):
        tiny_queue = queue.Queue(maxsize=1)
        with patch.object(jobs, 'Q', tiny_queue):
            with self.assertRaisesRegex(ValueError, '排队'):
                jobs.submit_many(self.user, self.project, 'create', [{'requirements': 'one'}, {'requirements': 'two'}])
        jobs.run(tiny_queue.get_nowait())  # rolled-back handoff is harmless
        with D.db() as c:
            self.assertEqual(tuple(c.execute('SELECT balance,frozen FROM credit_accounts').fetchone()), (300, 0))
            self.assertEqual(c.execute('SELECT count(*) FROM tasks').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM credit_ledger WHERE kind="FREEZE"').fetchone()[0], 0)

    def test_original_duplicate_ignores_new_server_generated_source_id(self):
        payload = {'source_id': D.uid(), 'brief': {'platform': 'xhs', 'topic': '咖啡'}, 'temporary': '自己的资料'}
        jobs.submit(self.user, self.project, 'original', payload)
        with self.assertRaisesRegex(ValueError, '相同任务'):
            jobs.submit(self.user, self.project, 'original', {**payload, 'source_id': D.uid()})

    def test_same_request_is_allowed_after_cancel_and_in_other_project(self):
        payload = {'requirements': 'one'}
        first = jobs.submit(self.user, self.project, 'create', payload)
        jobs.cancel(first, self.user)
        second = jobs.submit(self.user, self.project, 'create', payload)
        other = D.uid()
        with D.db() as c:
            c.execute('INSERT INTO projects VALUES (?,?,?,?,?)', (other, self.user, 'another', '', D.now()))
        third = jobs.submit(self.user, other, 'create', payload)
        self.assertEqual(len({first, second, third}), 3)

    def test_cleanup_preserves_inputs_of_still_running_tasks(self):
        ident = jobs.submit(self.user, self.project, 'create', {'temporary': 'still needed'})
        with D.db() as c:
            c.execute('UPDATE tasks SET updated_at=? WHERE id=?', ('2020-01-01T00:00:00+00:00', ident))
        maintenance.cleanup()
        with D.db() as c:
            payload = json.loads(c.execute('SELECT payload FROM tasks WHERE id=?', (ident,)).fetchone()[0])
        self.assertEqual(payload['temporary'], 'still needed')
        self.assertIn('asset_snapshot', payload)

    def test_expired_snapshot_cannot_retain_deleted_private_asset(self):
        aid = D.uid()
        with D.db() as c:
            c.execute('INSERT INTO assets VALUES (?,?,?,?,?,?)', (aid, self.project, '客户内部资料', '品牌资料', 'PRIVATE-SNAPSHOT-SECRET', D.now()))
        ident = jobs.submit(self.user, self.project, 'create', {'assets': [aid]})
        jobs.fail(ident, 'test')
        with D.db() as c:
            c.execute('DELETE FROM assets WHERE id=?', (aid,))
            c.execute('UPDATE tasks SET updated_at=? WHERE id=?', ('2020-01-01T00:00:00+00:00', ident))
        maintenance.cleanup()
        with D.db() as c:
            payload = c.execute('SELECT payload FROM tasks WHERE id=?', (ident,)).fetchone()[0]
        self.assertNotIn('PRIVATE-SNAPSHOT-SECRET', payload)


class AdversarialTransport(unittest.TestCase):
    def test_private_dns_target_rejected_before_socket_connection(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('127.0.0.1', 443))]
        with patch('socket.getaddrinfo', return_value=addresses), patch('socket.socket', side_effect=AssertionError('private socket attempted')) as sock, patch('urllib.request.getproxies', return_value={}):
            with self.assertRaises(ValueError):
                adapters.download_media('https://media.attacker.example/video.mp4')
            sock.assert_not_called()

    def test_dns_mixed_public_private_answers_fail_closed(self):
        for private in ('10.1.2.3', '169.254.169.254', '127.0.0.1', '::1', 'fc00::1'):
            addresses = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', (host, 443)) for host in ('8.8.8.8', private)]
            with self.subTest(private=private), patch('socket.getaddrinfo', return_value=addresses), patch('socket.socket') as sock:
                with self.assertRaises(ValueError):
                    adapters.public_connection(('cdn.example', 443))
                sock.assert_not_called()

    def test_dns_pinning_keeps_original_tls_hostname(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('8.8.8.8', 443))]
        context = MagicMock()
        conn = adapters.PublicHTTPSConnection('cdn.example', timeout=5, context=context)
        with patch('socket.getaddrinfo', return_value=addresses) as dns, patch('socket.socket') as sock:
            conn.connect()
            dns.assert_called_once_with('cdn.example', 443, 0, socket.SOCK_STREAM)
            sock.return_value.connect.assert_called_once_with(('8.8.8.8', 443))
            context.wrap_socket.assert_called_once_with(sock.return_value, server_hostname='cdn.example')

    def test_transport_closes_socket_on_connect_failure(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, '', ('8.8.8.8', 443))]
        with patch('socket.getaddrinfo', return_value=addresses), patch('socket.socket') as sock:
            sock.return_value.connect.side_effect = TimeoutError('injected timeout')
            with self.assertRaises(TimeoutError):
                adapters.public_connection(('cdn.example', 443))
            sock.return_value.close.assert_called_once()

    def test_media_redirects_reject_credentials_private_literals_and_http(self):
        import urllib.request
        req = urllib.request.Request('https://cdn.example/video')
        for target in ('https://localhost./secret', 'https://127.0.0.1/secret', 'http://cdn.example/video', 'https://user:pass@cdn.example/video'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                adapters.HttpsOnlyRedirect().redirect_request(req, None, 302, 'Moved', {}, target)

    def test_bounded_reader_rejects_slow_stream_and_accepts_limit(self):
        self.assertEqual(adapters.read_bounded(io.BytesIO(b'abcd'), 4, 1), b'abcd')
        with self.assertRaises(ValueError):
            adapters.read_bounded(io.BytesIO(b'abcde'), 4, 1)
        with patch.object(adapters.time, 'monotonic', side_effect=[0, 0, 2]):
            with self.assertRaises(TimeoutError):
                adapters.read_bounded(io.BytesIO(b'abc'), 10, 1)

    def test_external_json_response_is_size_bounded(self):
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b' ' * (8 * 1024 * 1024 + 1))
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, '上限|过大'):
                adapters.request_json('https://provider.example/api')

    def test_wrong_hook_type_rejected_by_model_validator(self):
        outputs = adapters.demo_outputs('douyin', 'coffee', 1)
        outputs[0]['hook'] = {'malformed': 'hook'}
        with self.assertRaises(ValueError):
            adapters.validate_creation({'outputs': outputs}, 'douyin')

    def test_optional_douyin_comment_layout_cannot_crash_annotation(self):
        outputs = adapters.demo_outputs('douyin', 'coffee', 1)
        outputs[0]['comment_layout'] = 'not an object'
        with self.assertRaises(ValueError):
            adapters.validate_grounded_creation({'outputs': outputs}, 'douyin', [], [])

    def test_cancelled_task_never_retries_paid_request_and_scope_resets(self):
        active = True
        def request(*args):
            nonlocal active
            active = False
            raise TimeoutError('injected late upstream failure')
        options = [('one', {'base_url': 'https://provider.example', 'api_key': 'test'}, 'test')]
        with patch.object(adapters, 'candidates', return_value=options), patch.object(adapters, 'setting', return_value={'retries': 2, 'timeout': 1}), patch.object(adapters, 'request_json', side_effect=request) as req:
            with adapters.task_scope(lambda: active), self.assertRaises(adapters.TaskCancelled):
                adapters.model_json({}, {}, 'rules')
            req.assert_called_once()
        adapters.ensure_task_active()  # no leaked cancellation into the next job

    def test_demo_public_copy_does_not_expose_internal_strategy_labels(self):
        from server.content_quality import public_text
        for platform in ('xhs', 'douyin'):
            outputs = adapters.demo_outputs(platform, '咖啡', 1)
            adapters.validate_creation({'outputs': outputs}, platform)
            for output in outputs:
                self.assertTrue(output['demo'])
                self.assertIn('演示', output['body'])
                for jargon in ('钓鱼帖', '提问截流', '岗位', '切角', '建立信任'):
                    self.assertNotIn(jargon, public_text(output))


if __name__ == '__main__':
    unittest.main()
