import base64
import hashlib
import hmac
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET = b'12345678901234567890'


def totp():
    digest = hmac.new(SECRET, struct.pack('>Q', int(time.time()) // 30), hashlib.sha1).digest()
    offset = digest[-1] & 15
    return f'{(struct.unpack(">I", digest[offset:offset+4])[0] & 0x7fffffff) % 1000000:06d}'


class MFAHttpTests(unittest.TestCase):
    def test_admin_login_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            env = {**os.environ, 'PORT': str(port), 'DAOLOOK_DB': str(Path(folder)/'db'), 'DAOLOOK_MODE':'demo', 'DAOLOOK_ADMIN_EMAIL':'admin@mfa.test', 'DAOLOOK_ADMIN_PASSWORD':'strong-admin-password', 'DAOLOOK_ADMIN_TOTP_SECRET':base64.b32encode(SECRET).decode(), 'DAOLOOK_SECURE_COOKIE':'0', 'DAOLOOK_PUBLIC_ORIGIN':''}
            proc = subprocess.Popen([sys.executable, '-m', 'server.app'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            def request(path, data=None, cookie=None):
                headers={'Content-Type':'application/json'}
                if cookie: headers['Cookie']=cookie
                req=urllib.request.Request(f'http://127.0.0.1:{port}'+path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=2) as response:
                        return response.status, response.headers, json.loads(response.read())
                except urllib.error.HTTPError as response:
                    with response:
                        return response.code, response.headers, json.loads(response.read())
            try:
                for _ in range(100):
                    try:
                        request('/api/public'); break
                    except OSError:
                        time.sleep(.05)
                credentials={'email':'admin@mfa.test', 'password':'strong-admin-password'}
                self.assertEqual(request('/api/auth/login', credentials)[0], 401)
                code=totp()
                status, headers, _ = request('/api/auth/login', {**credentials, 'totp':code})
                self.assertEqual(status, 200)
                cookie=headers['Set-Cookie'].split(';', 1)[0]
                self.assertEqual(request('/api/admin', cookie=cookie)[0], 200)
                self.assertEqual(request('/api/auth/login', {**credentials, 'totp':code})[0], 401)
                self.assertEqual(request('/api/admin/config', {'mode':'live'}, cookie)[0], 400)
                ordinary = {'email':'person@mfa.test', 'password':'ordinary-password'}
                status, headers, _ = request('/api/auth/register', ordinary)
                self.assertEqual(status, 200)
                first = headers['Set-Cookie'].split(';', 1)[0]
                user_id = request('/api/bootstrap', cookie=first)[2]['user']['id']
                status, headers, _ = request('/api/auth/login', ordinary)
                self.assertEqual(status, 200)
                second = headers['Set-Cookie'].split(';', 1)[0]
                self.assertEqual(request('/api/auth/logout-others', {}, first)[0], 200)
                self.assertEqual(request('/api/bootstrap', cookie=second)[0], 401)
                self.assertEqual(request('/api/bootstrap', cookie=first)[0], 200)
                self.assertEqual(request('/api/admin/user/delete', {'user_id':user_id}, first)[0], 403)
                self.assertEqual(request('/api/admin/user/delete', {'user_id':user_id}, cookie)[0], 200)
                self.assertEqual(request('/api/bootstrap', cookie=first)[0], 401)
            finally:
                proc.terminate(); proc.wait(timeout=5)
