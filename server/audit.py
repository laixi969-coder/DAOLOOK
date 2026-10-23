"""Audit privileged changes without recording credentials or request bodies."""
import logging
from .db import uid, now, dumps

LOG = logging.getLogger('daolook')


def record(c, actor, action, target='', details=None, request_id=''):
    ident = uid()
    c.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?,?)',
              (ident, actor, action, str(target or ''), dumps(details or {}), request_id, now()))
    return ident


def event(name, **fields):
    LOG.warning(dumps({'event': name, 'at': now(), **fields}))
