"""Explicit permission to turn an account's balance into real provider work.

Call these helpers inside the caller's write transaction. Ordinary legacy users
are deliberately unapproved; changing the site's mode never grants permission.
"""
from .db import now, ledger
from . import audit


def initialize(c):
    c.execute('CREATE TABLE IF NOT EXISTS live_accounts(user_id TEXT PRIMARY KEY REFERENCES users(id),source TEXT NOT NULL,approved_by TEXT NOT NULL,approved_at TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS demo_accounts(user_id TEXT PRIMARY KEY REFERENCES users(id))')
    # Older generated demo identities had no persisted provenance marker.
    c.execute("INSERT OR IGNORE INTO demo_accounts SELECT id FROM users WHERE role!='admin' AND email GLOB 'demo-*@daolook.local'")
    c.execute("INSERT OR IGNORE INTO live_accounts SELECT id,'legacy_admin',id,? FROM users WHERE role='admin' AND id NOT IN (SELECT user_id FROM demo_accounts)", (now(),))


def create(c, user, demo=False, verified=False, role='user'):
    account = c.execute('SELECT role FROM users WHERE id=?', (user,)).fetchone()
    if not account:
        raise ValueError('账号不存在')
    if demo:
        c.execute('INSERT OR IGNORE INTO demo_accounts VALUES (?)', (user,))
    elif verified or account['role'] == 'admin':
        source = 'admin_created' if account['role'] == 'admin' else 'mailbox_verified'
        c.execute('INSERT OR IGNORE INTO live_accounts VALUES (?,?,?,?)', (user, source, user, now()))


def require_live(c, user):
    account = c.execute('SELECT role FROM users WHERE id=?', (user,)).fetchone()
    if not account or c.execute('SELECT 1 FROM demo_accounts WHERE user_id=?', (user,)).fetchone():
        raise ValueError('演示账号不能使用真实付费服务，请注册并验证正式账号')
    if account['role'] != 'admin' and not c.execute('SELECT 1 FROM live_accounts WHERE user_id=?', (user,)).fetchone():
        raise ValueError('账号尚未验证或获准使用真实服务，请验证邮箱或联系管理员')


def approve(c, user, actor, source, preserve_balance=False, request_id=''):
    if type(preserve_balance) is not bool:
        raise ValueError('是否保留原有积分必须明确为是或否')
    account = c.execute('SELECT balance,frozen FROM credit_accounts WHERE user_id=?', (user,)).fetchone()
    if not account:
        raise ValueError('账号不存在')
    if c.execute('SELECT 1 FROM demo_accounts WHERE user_id=?', (user,)).fetchone():
        raise ValueError('生成的演示账号不能转为正式账号，请注册并验证正式账号')
    operator = c.execute('SELECT role FROM users WHERE id=?', (actor,)).fetchone()
    if not operator or (operator['role'] != 'admin' and (preserve_balance or actor != user)):
        raise ValueError('只有管理员能批准其他账号或明确保留原有积分')
    if not isinstance(source, str) or not source.strip() or len(source) > 80:
        raise ValueError('账号批准来源无效')
    if account['frozen'] or c.execute("SELECT 1 FROM tasks WHERE user_id=? AND state NOT IN ('SUCCEEDED','PARTIAL','FAILED','CANCELLED') LIMIT 1", (user,)).fetchone():
        raise ValueError('账号仍有进行中的任务，请等待结束后再开通真实服务')
    if c.execute('SELECT 1 FROM live_accounts WHERE user_id=?', (user,)).fetchone():
        return False
    previous = account['balance']
    if not preserve_balance and previous:
        c.execute('UPDATE credit_accounts SET balance=0 WHERE user_id=?', (user,))
        ledger(c, user, None, 'DEDUCT', -previous, '开通真实服务，清除未核验的历史体验积分')
    c.execute('INSERT INTO live_accounts VALUES (?,?,?,?)', (user, source, actor, now()))
    audit.record(c, actor, 'account.live_approved', user,
                 {'source': source, 'preserve_balance': bool(preserve_balance),
                  'previous_balance': previous, 'balance': previous if preserve_balance else 0}, request_id)
    return True
