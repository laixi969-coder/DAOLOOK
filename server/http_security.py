"""Small, bounded HTTP safeguards. Public deployments still require an edge proxy."""
import hashlib
import ipaddress
import math
import os
import threading
import time
from collections import OrderedDict
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit


class Rejected(Exception):
    def __init__(self, message, status=400, headers=None):
        self.message, self.status, self.headers = message, status, headers or {}


class RateLimiter:
    """Thread-safe token buckets; never evict a live bucket to admit a new identity."""
    def __init__(self, max_keys=20000, clock=time.monotonic):
        self.buckets = OrderedDict()
        self.lock = threading.Lock()
        self.max_keys, self.clock = max_keys, clock

    def clear(self):
        with self.lock:
            self.buckets.clear()

    def check(self, key, limit, seconds=60):
        with self.lock:
            stamp = self.clock()
            while self.buckets and next(iter(self.buckets.values()))[2] <= stamp:
                self.buckets.popitem(last=False)
            old = self.buckets.get(key)
            if old is None and len(self.buckets) >= self.max_keys:
                raise Rejected('服务繁忙，请一分钟后重试', 429, {'Retry-After': '60'})
            tokens = limit if old is None else min(limit, old[0] + (stamp - old[1]) * limit / seconds)
            allowed = tokens >= 1
            # Uniform idle expiry preserves OrderedDict ordering across bucket windows.
            self.buckets[key] = (tokens - 1 if allowed else tokens, stamp, stamp + 600)
            self.buckets.move_to_end(key)
            if not allowed:
                retry = max(1, math.ceil((1 - tokens) * seconds / limit))
                raise Rejected(f'操作较频繁，请 {retry} 秒后重试', 429, {'Retry-After': str(retry)})


def client_ip(peer, headers):
    """Honor exactly one proxy-provided address only from explicitly trusted peers."""
    networks = os.environ.get('DAOLOOK_TRUSTED_PROXIES', '').split(',')
    try:
        trusted = any(ipaddress.ip_address(peer) in ipaddress.ip_network(n.strip()) for n in networks if n.strip())
    except ValueError:
        trusted = False  # A misconfigured trust list must never grant more trust.
    if trusted:
        value = headers.get('X-Real-IP', '')
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
    return peer


def validate_request(headers, method):
    host_values = headers.get_all('Host', [])
    host = headers.get('Host', '')
    if len(host_values) != 1 or any(c.isspace() for c in host) or any(c in host for c in '/\\@?#,'):
        raise Rejected('请求地址无效')
    try:
        host_url = urlsplit('http://' + host)
        if not host_url.hostname or host_url.port == 0:
            raise ValueError()
    except ValueError:
        raise Rejected('请求地址无效')
    public_origin = os.environ.get('DAOLOOK_PUBLIC_ORIGIN', '').rstrip('/')
    if public_origin and host.lower() != urlsplit(public_origin).netloc.lower():
        raise Rejected('请求地址未获授权', 403)
    if headers.get_all('Transfer-Encoding') or len(headers.get_all('Content-Length', [])) > 1:
        raise Rejected('请求长度无效')
    raw_length = headers.get('Content-Length', '0')
    if not raw_length.isascii() or not raw_length.isdecimal() or len(raw_length) > 10:
        raise Rejected('请求长度无效')
    length = int(raw_length)
    if length > 3_000_000:
        raise Rejected('文件过大，请控制在 2 MB 以内', 413)
    if method in ('GET', 'HEAD'):
        if length:
            raise Rejected('此请求不接受正文')
        return 0
    if len(headers.get_all('Origin', [])) > 1:
        raise Rejected('跨站请求已拒绝', 403)
    origin = headers.get('Origin')
    if origin:
        parsed = urlsplit(origin)
        expected_scheme = urlsplit(public_origin).scheme if public_origin else ('https' if os.environ.get('DAOLOOK_SECURE_COOKIE') == '1' else 'http')
        if (parsed.scheme != expected_scheme or parsed.netloc.lower() != host.lower()
                or parsed.path or parsed.query or parsed.fragment or parsed.username):
            raise Rejected('跨站请求已拒绝', 403)
    if headers.get('Sec-Fetch-Site') == 'cross-site':
        raise Rejected('跨站请求已拒绝', 403)
    # Non-browser clients can omit Origin, but browser-simple form requests cannot mutate.
    if length and headers.get_content_type() != 'application/json':
        raise Rejected('请求内容需要使用 JSON 格式', 415)
    return length


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(self, *args, max_connections=None, **kwargs):
        limit = max_connections if max_connections is not None else int(os.environ.get('DAOLOOK_HTTP_CONNECTIONS', '64'))
        if not 1 <= limit <= 1024:
            raise ValueError('DAOLOOK_HTTP_CONNECTIONS must be between 1 and 1024')
        self.slots = threading.BoundedSemaphore(limit)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            try:
                request.settimeout(0.1)
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nRetry-After: 5\r\nCache-Control: no-store\r\nContent-Length: 0\r\n\r\n')
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class StaticCache:
    """Cache only public web files, bounded in total bytes and entry count."""
    def __init__(self, max_bytes=8 * 1024 * 1024, max_entries=64):
        self.entries, self.size = OrderedDict(), 0
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.lock = threading.Lock()

    def read(self, path):
        stat = path.stat()
        stamp = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size, stat.st_ino)
        with self.lock:
            old = self.entries.get(path)
            if old and old[0] == stamp:
                self.entries.move_to_end(path)
                return old[1:]
            if old:
                self.size -= len(self.entries.pop(path)[1])
            body = path.read_bytes()
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            if len(body) <= self.max_bytes:
                while self.entries and (self.size + len(body) > self.max_bytes or len(self.entries) >= self.max_entries):
                    self.size -= len(self.entries.popitem(last=False)[1][1])
                self.entries[path] = (stamp, body, etag)
                self.size += len(body)
            return body, etag
