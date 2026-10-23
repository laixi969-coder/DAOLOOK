"""Private sidecar secrets. SQLite and ordinary DB backups contain references only.

DAOLOOK_SECRETS_DIR may point at a separately managed, private mounted directory.
This is file isolation, not encryption or a replacement for a cloud secret manager.
"""
import os
import re
import secrets
import tempfile
from pathlib import Path
from .config import private_directory, sync_directory

PREFIX = 'secret-file:'


def directory():
    from . import db as database
    path = Path(os.environ.get('DAOLOOK_SECRETS_DIR', str(Path(database.DB_PATH).resolve().parent / 'secrets')))
    return private_directory(path)


def read(value):
    if not isinstance(value, str) or not value.startswith(PREFIX):
        return value
    ident = value[len(PREFIX):]
    if not re.fullmatch('[a-f0-9]{64}', ident):
        raise ValueError('凭证引用无效')
    path = directory() / ident
    if not path.is_file() or path.is_symlink():
        raise ValueError('服务凭证缺失，请恢复私有凭证目录或重新配置')
    path.chmod(0o600)
    return path.read_text()


def write(value):
    if not value or value.startswith(PREFIX):
        return value
    folder = directory()
    # Never overwrite a referenced file before its DB transaction commits.
    ident = secrets.token_hex(32)
    fd, temporary = tempfile.mkstemp(dir=folder)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, folder / ident)
        # The DB may commit this reference immediately after return. Persist the
        # directory entry as well as the secret bytes before publishing it.
        sync_directory(folder)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return PREFIX + ident


def pack(key, value):
    value = dict(value)
    field = 'password' if key == 'mail' else 'api_key'
    if field in value:
        value[field] = write(value[field])
    return value


def unpack(key, value):
    if key in ('mail', 'provider', 'tikhub'):
        value = dict(value)
        field = 'password' if key == 'mail' else 'api_key'
        value[field] = read(value.get(field, ''))
    return value
