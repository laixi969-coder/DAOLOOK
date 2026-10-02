"""Adversarial HTTP tests: isolated loopback server, no production DB or providers."""
import http.client
import importlib
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from server import app

class HTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        database = importlib.import_module('server.db')
        self.db_patch = patch.object(database, 'DB_PATH', str(Path(self.tmp.name) / 'http.db'))
        self.db_patch.start()
        database.init()
        app.RATE.clear()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.db_patch.stop()
        self.tmp.cleanup()

    def request(self, path, method='GET', body=None, headers=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_static_revalidation_and_private_api(self):
        status, headers, body = self.request('/app.js')
        self.assertEqual(status, 200)
        self.assertIn('ETag', headers)
        self.assertEqual(headers['Cache-Control'], 'public, no-cache')
        status, headers2, body2 = self.request('/app.js', headers={'If-None-Match': headers['ETag']})
        self.assertEqual((status, body2), (304, b''))
        self.assertEqual(headers2['ETag'], headers['ETag'])
        status, headers, _ = self.request('/api/bootstrap')
        self.assertEqual(status, 401)
        self.assertEqual(headers['Cache-Control'], 'private, no-store')

    def test_simple_content_type_cannot_mutate(self):
        status, _, _ = self.request('/api/auth/demo', 'POST', '{}', {'Content-Type': 'text/plain'})
        self.assertEqual(status, 415)

    def test_cross_site_fetch_without_origin_rejected(self):
        status, _, _ = self.request('/api/auth/demo', 'POST', '{}', {'Content-Type': 'application/json', 'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(status, 403)

    def test_ambiguous_content_length_rejected(self):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        conn.putrequest('POST', '/api/auth/logout')
        conn.putheader('Content-Type', 'application/json')
        conn.putheader('Content-Length', '2')
        conn.putheader('Content-Length', '2')
        conn.endheaders(b'{}')
        response = conn.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        conn.close()

    def test_chunked_encoding_rejected(self):
        status, _, _ = self.request('/api/auth/logout', 'POST', '{}', {'Transfer-Encoding': 'chunked', 'Content-Type': 'application/json'})
        self.assertEqual(status, 400)

    def test_demo_creation_is_rate_limited(self):
        with patch.object(app, 'new_user', return_value='demo'), patch.object(app.Handler, 'session', return_value={}):
            statuses = [self.request('/api/auth/demo', 'POST', '{}', {'Content-Type': 'application/json'})[0] for _ in range(31)]
        self.assertEqual(statuses[-1], 429)


    def test_large_headers_and_deep_json_fail_cleanly(self):
        status, headers, _ = self.request('/api/health', headers={'X-Fill': 'x' * 33000})
        self.assertEqual(status, 431)
        self.assertEqual(headers['Cache-Control'], 'private, no-store')
        status, _, _ = self.request('/api/auth/logout', 'POST', '[' * 1500 + '0' + ']' * 1500, {'Content-Type': 'application/json'})
        self.assertEqual(status, 400)

    def test_queue_capacity_errors_keep_status_and_retry_guidance(self):
        from server.jobs import TaskAdmissionError
        for status, retry in ((429, 30), (503, 30), (409, None)):
            with patch.object(app.Handler, 'api', side_effect=TaskAdmissionError('请稍后重试', status, retry)):
                result, headers, body = self.request('/api/health')
            self.assertEqual(result, status)
            self.assertEqual(headers.get('Retry-After'), str(retry) if retry is not None else None)
            self.assertEqual(json.loads(body)['error'], '请稍后重试')

    def test_origin_and_proxy_host_validation(self):
        import os
        with patch.dict(os.environ, {'DAOLOOK_PUBLIC_ORIGIN': 'https://daolook.example'}):
            self.assertEqual(self.request('/api/health')[0], 403)
            self.assertEqual(self.request('/api/health', headers={'Host': 'daolook.example'})[0], 200)
            for origin in ('https://attacker.example', 'http://daolook.example', 'null', 'https://daolook.example@attacker.example'):
                self.assertEqual(self.request('/api/auth/logout', 'POST', '{}', {'Host': 'daolook.example', 'Origin': origin, 'Content-Type': 'application/json'})[0], 403)
            self.assertEqual(self.request('/api/auth/logout', 'POST', '{}', {'Host': 'daolook.example', 'Origin': 'https://daolook.example', 'Content-Type': 'application/json'})[0], 200)

    def test_project_edit_is_persistent_validated_and_owner_only(self):
        status, headers, _ = self.request('/api/auth/demo', 'POST', '{}', {'Content-Type': 'application/json'})
        self.assertEqual(status, 200)
        cookie = headers['Set-Cookie'].split(';')[0]
        auth = {'Cookie': cookie, 'Content-Type': 'application/json'}
        project = json.loads(self.request('/api/bootstrap', headers=auth)[2])['projects'][0]['id']
        data = {'name': '我的咖啡店', 'description': '给附近上班族的精品咖啡'}
        self.assertEqual(self.request('/api/projects/' + project, 'PATCH', json.dumps(data), auth)[0], 200)
        updated = json.loads(self.request('/api/bootstrap', headers=auth)[2])['projects'][0]
        self.assertEqual((updated['name'], updated['description']), (data['name'], data['description']))
        for invalid in ({'name': ''}, {'name': 'x' * 101}, {'name': 'ok', 'description': []}, {'name': 'ok', 'description': 'x' * 2001}):
            self.assertEqual(self.request('/api/projects/' + project, 'PATCH', json.dumps(invalid), auth)[0], 400)
        other = self.request('/api/auth/demo', 'POST', '{}', {'Content-Type': 'application/json'})[1]['Set-Cookie'].split(';')[0]
        self.assertEqual(self.request('/api/projects/' + project, 'PATCH', json.dumps(data), {'Cookie': other, 'Content-Type': 'application/json'})[0], 404)


class SecurityPrimitiveTests(unittest.TestCase):
    def test_rate_limiter_is_atomic_recovers_and_bounds_identity_memory(self):
        from concurrent.futures import ThreadPoolExecutor
        from server.http_security import RateLimiter, Rejected
        clock = [0.0]
        limiter = RateLimiter(max_keys=2, clock=lambda: clock[0])
        def attempt(_):
            try:
                limiter.check('same-account', 5)
                return True
            except Rejected:
                return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(sum(pool.map(attempt, range(30))), 5)
        limiter.check('second', 1)
        with self.assertRaises(Rejected):
            limiter.check('third', 1)
        self.assertEqual(len(limiter.buckets), 2)
        clock[0] = 12
        limiter.check('same-account', 5)
        clock[0] = 613
        limiter.check('third', 1)
        self.assertEqual(len(limiter.buckets), 1)

    def test_proxy_identity_requires_trusted_peer(self):
        from server.http_security import client_ip
        import os
        headers = {'X-Real-IP': '198.51.100.3', 'X-Forwarded-For': '203.0.113.4'}
        with patch.dict(os.environ, {'DAOLOOK_TRUSTED_PROXIES': ''}):
            self.assertEqual(client_ip('127.0.0.1', headers), '127.0.0.1')
        with patch.dict(os.environ, {'DAOLOOK_TRUSTED_PROXIES': '127.0.0.1/32'}):
            self.assertEqual(client_ip('127.0.0.1', headers), '198.51.100.3')
            self.assertEqual(client_ip('192.0.2.1', headers), '192.0.2.1')
            self.assertEqual(client_ip('127.0.0.1', {'X-Real-IP': 'fake'}), '127.0.0.1')

    def test_static_cache_invalidates_and_bounds_bytes(self):
        from server.http_security import StaticCache
        cache = StaticCache(max_bytes=8, max_entries=1)
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / 'one.js', Path(directory) / 'two.js'
            first.write_bytes(b'old')
            old_body, old_etag = cache.read(first)
            first.write_bytes(b'new')
            self.assertNotEqual(old_etag, cache.read(first)[1])
            second.write_bytes(b'second')
            cache.read(second)
            self.assertEqual(len(cache.entries), 1)
            self.assertLessEqual(cache.size, 8)
            second.write_bytes(b'x' * 20)
            self.assertEqual(cache.read(second)[0], b'x' * 20)
            self.assertEqual(cache.size, 0)

    def test_connections_are_bounded_and_slow_clients_released(self):
        import socket
        import time
        from server.http_security import BoundedHTTPServer
        class FastDeadlineHandler(app.Handler):
            request_read_timeout = 0.2
        server = BoundedHTTPServer(('127.0.0.1', 0), FastDeadlineHandler, max_connections=1)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        first = socket.create_connection(server.server_address, timeout=2)
        second = None
        try:
            first.sendall(b'GET / HTTP/1.1\r\nHost:')
            time.sleep(0.03)
            second = socket.create_connection(server.server_address, timeout=2)
            self.assertIn(b'503 Service Unavailable', second.recv(1024))
            time.sleep(0.25)
            self.assertEqual(first.recv(1024), b'')
            connection = http.client.HTTPConnection(*server.server_address, timeout=2)
            connection.request('GET', '/api/health')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            response.read()
            connection.close()
        finally:
            first.close()
            if second:
                second.close()
            server.shutdown()
            server.server_close()
            thread.join()

if __name__ == '__main__':
    unittest.main()
