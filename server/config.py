"""Shared startup configuration and private local-file permissions."""
import os
import stat
import tempfile
import fcntl
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path=None):
    path = Path(path or ROOT / '.env')
    if path.is_file():
        path.chmod(0o600)
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('\"').strip("'"))


def database_path():
    path = Path(os.environ.get('DAOLOOK_DB', 'data/daolook.db')).expanduser()
    return path if path.is_absolute() else ROOT / path


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_directory(path):
    """Create private storage, but never chmod an operator's existing directory."""
    path = Path(path).expanduser().absolute()
    protected = {Path('/'), Path.home().resolve(), ROOT.resolve(), Path('/tmp').resolve(),
                 Path(tempfile.gettempdir()).resolve()}
    if path.resolve() in protected or path.is_symlink():
        raise ValueError('存储需要独立的私有目录，不能使用根目录、HOME、项目目录、临时目录或符号链接')
    missing = []
    current = path
    while not current.exists():
        if current.is_symlink():
            raise ValueError('存储目录不能是符号链接')
        missing.append(current)
        current = current.parent
    for folder in reversed(missing):
        try:
            folder.mkdir(mode=0o700)
        except FileExistsError:
            pass
        sync_directory(folder.parent)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077:
        raise ValueError('存储需要权限为 0700 的独立目录；请先确认目录用途并由管理员设置权限：' + str(path))
    return path


def protect_database(path):
    path = Path(path)
    private_directory(path.parent)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        if path.is_symlink():
            raise ValueError('数据库路径不能是符号链接')
    else:
        os.close(fd)
    for suffix in ('', '-wal', '-shm'):
        file = Path(str(path) + suffix)
        try:
            if file.is_symlink():
                raise ValueError('数据库及其附属文件不能是符号链接')
            file.chmod(0o600)
        except FileNotFoundError:
            pass


@contextmanager
def instance_lock(path):
    """Hold an exclusive lock for the lifetime of the server using this database."""
    path = Path(path).expanduser().absolute()
    private_directory(path.parent)
    lock_path = path.parent / (path.name + '.instance.lock')
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if os.fstat(fd).st_nlink != 1:
            raise ValueError('实例锁文件无效')
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError('该数据库已有运行中的 DAOLOOK 服务，拒绝重复启动') from exc
        yield
    finally:
        os.close(fd)
