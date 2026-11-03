"""TOTP verification for the installation's administrator account."""
import base64
import hashlib
import hmac
import os
import re
import struct
import time
from urllib.parse import urlsplit


def secret_bytes():
    value = os.environ.get('DAOLOOK_ADMIN_TOTP_SECRET', '').replace(' ', '').upper()
    if not value or not re.fullmatch(r'[A-Z2-7]+', value):
        raise ValueError('请设置有效的 DAOLOOK_ADMIN_TOTP_SECRET')
    try:
        key = base64.b32decode(value + '=' * (-len(value) % 8), casefold=True)
    except (ValueError, TypeError) as exc:
        raise ValueError('管理员 TOTP 密钥格式无效') from exc
    if len(key) < 20:
        raise ValueError('管理员 TOTP 密钥至少需要 20 随机字节')
    return key


def configured():
    return bool(os.environ.get('DAOLOOK_ADMIN_TOTP_SECRET', ''))


def fingerprint():
    return hashlib.sha256(secret_bytes()).hexdigest()


def validate_live_security():
    secret_bytes()
    if os.environ.get('DAOLOOK_SECURE_COOKIE') != '1':
        raise ValueError('真实服务需要 DAOLOOK_SECURE_COOKIE=1 和 HTTPS')
    origin = urlsplit(os.environ.get('DAOLOOK_PUBLIC_ORIGIN', ''))
    try:
        valid = origin.scheme == 'https' and origin.hostname and not origin.username and not origin.password and not origin.path and not origin.query and not origin.fragment and origin.port != 0
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('真实服务需要有效的 HTTPS DAOLOOK_PUBLIC_ORIGIN')


def verify(c, user, code):
    key = secret_bytes()
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{6}', code):
        return False
    current = int(time.time()) // 30
    matched = None
    for counter in (current - 1, current, current + 1):
        digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
        offset = digest[-1] & 15
        number = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000
        if hmac.compare_digest(f'{number:06d}', code):
            matched = counter
    if matched is None:
        return False
    c.execute('INSERT OR IGNORE INTO admin_totp_counters(user_id,last_counter) VALUES (?, -1)', (user,))
    return bool(c.execute('UPDATE admin_totp_counters SET last_counter=? WHERE user_id=? AND last_counter<?', (matched, user, matched)).rowcount)
