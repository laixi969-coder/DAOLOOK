"""Transactional deletion of one ordinary account and its owned workspace."""
import json
import secrets
from .db import db, dumps
from . import audit


def delete_user(user_id, actor, request_id=''):
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        account = c.execute('SELECT email,role FROM users WHERE id=?', (user_id,)).fetchone()
        if not account:
            raise ValueError('用户不存在')
        if account['role'] == 'admin':
            raise ValueError('不能通过此操作删除管理员账号')
        if c.execute("SELECT 1 FROM tasks WHERE user_id=? AND state NOT IN ('SUCCEEDED','PARTIAL','FAILED','CANCELLED')", (user_id,)).fetchone() or c.execute('SELECT 1 FROM credit_accounts WHERE user_id=? AND frozen!=0', (user_id,)).fetchone():
            raise ValueError('账号仍有进行中的任务或冻结积分，请等待结算')
        if c.execute("SELECT 1 FROM external_calls WHERE user_id=? AND state='started'", (user_id,)).fetchone():
            raise ValueError('账号仍有尚未完成的外部调用，请先核对并结算')
        projects = [r[0] for r in c.execute('SELECT id FROM projects WHERE user_id=?', (user_id,))]
        identifiers = [user_id, account['email'], *projects]
        for project in projects:
            for table in ('assets', 'asset_trash', 'source_contents', 'creation_outputs', 'generated_images', 'tasks', 'overseas_ideas'):
                identifiers.extend(r[0] for r in c.execute(f'SELECT id FROM {table} WHERE project_id=?', (project,)))
            for table in ('creation_revisions', 'creation_tracking', 'creation_results'):
                c.execute(f'DELETE FROM {table} WHERE creation_id IN (SELECT id FROM creation_outputs WHERE project_id=?)', (project,))
            for table in ('generated_images', 'asset_facts', 'asset_trash', 'overseas_ideas', 'overseas_searches'):
                c.execute(f'DELETE FROM {table} WHERE project_id=?', (project,))
            c.execute('DELETE FROM analysis_outputs WHERE source_id IN (SELECT id FROM source_contents WHERE project_id=?)', (project,))
            for table in ('creation_outputs', 'source_contents', 'assets', 'tasks'):
                c.execute(f'DELETE FROM {table} WHERE project_id=?', (project,))
        c.execute('DELETE FROM tasks WHERE user_id=?', (user_id,))
        c.execute('DELETE FROM projects WHERE user_id=?', (user_id,))
        for table in ('sessions', 'credit_ledger', 'credit_accounts', 'live_accounts', 'demo_accounts'):
            c.execute(f'DELETE FROM {table} WHERE user_id=?', (user_id,))
        c.execute('DELETE FROM email_codes WHERE email=?', (account['email'],))
        row = c.execute("SELECT value FROM settings WHERE key='signup'").fetchone()
        if row:
            signup = json.loads(row[0])
            signup['emails'] = [email for email in signup.get('emails', []) if str(email).strip().lower() != account['email']]
            c.execute("UPDATE settings SET value=? WHERE key='signup'", (dumps(signup),))
        # Preserve budget totals with an unlinkable replacement, not the identity.
        anonymous = secrets.token_hex(32)
        c.execute('UPDATE signup_grants SET user_id=? WHERE user_id=?', (anonymous, user_id))
        c.execute('UPDATE external_calls SET user_id=?, task_id=NULL WHERE user_id=?', (anonymous, user_id))
        for identifier in identifiers:
            c.execute('DELETE FROM audit_events WHERE actor_id=? OR target=? OR instr(details,?)>0', (identifier, identifier, identifier))
        c.execute('DELETE FROM users WHERE id=?', (user_id,))
        audit.record(c, actor, 'user.deleted', '', {'projects_deleted': len(projects)}, request_id)
