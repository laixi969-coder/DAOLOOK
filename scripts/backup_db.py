"""Validated, atomic SQLite snapshots. .env and the app use the same path rules.

Run daily: python3 scripts/backup_db.py --keep 30
Restore into a NEW directory: python3 scripts/backup_db.py --restore SNAPSHOT --db NEW/data.db
Existing storage directories must be private (0700); shared directories are never chmodded.
Secrets are separate: back up DAOLOOK_SECRETS_DIR through a private secret-backup channel.
"""
from contextlib import closing
import argparse
import datetime
import fcntl
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from server.config import load_env, database_path, private_directory, sync_directory
from contextlib import contextmanager


@contextmanager
def directory_lock(folder):
    folder = private_directory(folder)
    fd = os.open(folder / '.backup.lock', os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if os.fstat(fd).st_nlink != 1:
            raise ValueError('备份锁文件无效')
        os.fchmod(fd,0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield folder
    finally:
        os.close(fd)


def validate(connection):
    if connection.execute('PRAGMA integrity_check').fetchone()[0]!='ok':
        raise ValueError('数据库完整性检查失败')
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not tables:
        raise ValueError('源数据库没有任何表，拒绝生成空备份')
    if not {'users','projects','tasks','credit_accounts','settings','credit_ledger'}<=tables:
        raise ValueError('DAOLOOK 核心表缺失')
    if connection.execute('PRAGMA foreign_key_check').fetchone():
        raise ValueError('数据库存在外键错误')


def snapshot(source,target):
    source=Path(source).resolve()
    target=Path(target).expanduser().absolute()
    with directory_lock(target.parent):
        return _snapshot(source,target)


def _snapshot(source,target):
    if not source.is_file():
        raise ValueError('源数据库不存在，未生成备份：'+str(source))
    if source==target.resolve() or target.exists() or target.is_symlink():
        raise ValueError('目标必须是尚不存在的新文件')
    # SQLite will replay these files over an otherwise validated restored DB.
    if any(Path(str(target)+suffix).exists() or Path(str(target)+suffix).is_symlink()
           for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('恢复目标存在 SQLite 附属文件，请使用新的独立目录')
    fd,temporary=tempfile.mkstemp(prefix='.backup-',dir=target.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(temporary)) as dst:
            src.execute('BEGIN')
            validate(src)
            src.backup(dst)
            validate(dst)
        with open(temporary,'rb') as output:os.fsync(output.fileno())
        os.chmod(temporary,0o600)
        # Exclusive publication also protects concurrent runs from clobbering a restore target.
        os.link(temporary,target)
        sync_directory(target.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return target


def backup(source, folder, keep):
    if keep < 1:
        raise ValueError('--keep 必须至少为 1')
    source = Path(source).resolve()
    with directory_lock(folder) as folder:
        stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        target=_snapshot(source,folder/f'daolook-{stamp}.db')
        backups=sorted(path for path in folder.glob('daolook-*.db')
                       if re.fullmatch(r'daolook-\d{8}-\d{6}(?:-\d{6})?\.db',path.name)
                       and path.is_file() and not path.is_symlink() and path.resolve()!=source)
        for old in backups[:-keep]:
            if not any(Path(str(old)+suffix).exists() for suffix in ('-wal','-shm','-journal')):
                old.unlink()
        sync_directory(folder)
        return target


def main():
    load_env()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',default=str(database_path()))
    parser.add_argument('--dir',default=str(ROOT/'data/backups'))
    parser.add_argument('--keep',type=int,default=30)
    parser.add_argument('--restore')
    args=parser.parse_args()
    if args.keep<1:parser.error('--keep 必须至少为 1')
    try:
        if args.restore:
            target=snapshot(args.restore,args.db)
        else:
            target=backup(args.db,args.dir,args.keep)
    except (OSError,ValueError,sqlite3.Error) as exc:
        parser.exit(1,'备份/恢复失败：'+str(exc)+'\n')
    print(target)


if __name__=='__main__':main()
