"""Isolated storage regressions; no application data or external services."""
import concurrent.futures
from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch

from scripts.backup_db import backup, snapshot
from server.config import private_directory, protect_database
from server import secret_store


class DurabilityReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='daolook-durability-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = private_directory(self.root / 'source') / 'source.db'
        with closing(sqlite3.connect(self.source)) as connection, connection:
            for table in ('users', 'projects', 'tasks', 'credit_accounts', 'settings', 'credit_ledger'):
                connection.execute(f'CREATE TABLE {table}(value TEXT)')
            connection.execute("INSERT INTO users VALUES ('expected')")

    def test_shared_existing_directories_are_rejected_without_chmod(self):
        shared = self.root / 'shared'
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        with self.assertRaises(ValueError):
            protect_database(shared / 'db.sqlite')
        with self.assertRaises(ValueError):
            snapshot(self.source, shared / 'backup.db')
        with patch.dict(os.environ, {'DAOLOOK_SECRETS_DIR': str(shared)}):
            with self.assertRaises(ValueError):
                secret_store.write('fake-test-key')
        self.assertEqual(stat.S_IMODE(shared.stat().st_mode), 0o755)
        self.assertFalse((shared / 'db.sqlite').exists())
        self.assertEqual(list(shared.iterdir()), [])

    def test_new_storage_chain_is_private_and_symlink_directory_is_rejected(self):
        folder = private_directory(self.root / 'new' / 'nested')
        for directory in (folder, folder.parent):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        alias = self.root / 'alias'
        alias.symlink_to(folder, target_is_directory=True)
        with self.assertRaises(ValueError):
            private_directory(alias)

    def test_database_sidecar_symlink_is_not_chmodded(self):
        folder = private_directory(self.root / 'database')
        victim = self.root / 'unrelated'
        victim.write_text('keep')
        victim.chmod(0o644)
        Path(str(folder / 'db.sqlite') + '-wal').symlink_to(victim)
        with self.assertRaises(ValueError):
            protect_database(folder / 'db.sqlite')
        self.assertEqual(stat.S_IMODE(victim.stat().st_mode), 0o644)

    def test_secret_directory_entry_is_synced_before_reference_returns(self):
        folder = private_directory(self.root / 'secrets')
        real_fsync = os.fsync
        calls = []

        def observe(fd):
            calls.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
            return real_fsync(fd)

        with patch.dict(os.environ, {'DAOLOOK_SECRETS_DIR': str(folder)}), patch('os.fsync', side_effect=observe):
            reference = secret_store.write('fake-test-key')
            self.assertEqual(calls, ['file', 'directory'])
            self.assertEqual(secret_store.read(reference), 'fake-test-key')

    def test_restore_rejects_valid_stale_wal_and_shm(self):
        old = self.root / 'old.db'
        connection = sqlite3.connect(old)
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('PRAGMA wal_autocheckpoint=0')
            connection.execute('CREATE TABLE stale(value TEXT)')
            connection.execute("INSERT INTO stale VALUES ('wrong database')")
            connection.commit()
            folder = private_directory(self.root / 'restore')
            target = folder / 'restored.db'
            for suffix in ('-wal', '-shm'):
                shutil.copyfile(str(old) + suffix, str(target) + suffix)
            with self.assertRaises(ValueError):
                snapshot(self.source, target)
            self.assertFalse(target.exists())
        finally:
            connection.close()

    def test_restore_rejects_rollback_journal_and_broken_sidecar_link(self):
        folder = private_directory(self.root / 'restore')
        for suffix in ('-journal', '-wal'):
            target = folder / ('restore' + suffix + '.db')
            sidecar = Path(str(target) + suffix)
            sidecar.symlink_to(folder / 'missing')
            with self.assertRaises(ValueError):
                snapshot(self.source, target)
            self.assertFalse(target.exists())

    def test_parallel_rotation_is_serialized_and_preserves_unrelated_files(self):
        folder = private_directory(self.root / 'backups')
        unrelated = folder / 'daolook-business.db'
        unrelated.write_text('keep')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(backup, self.source, folder, 2) for _ in range(8)]
            for future in futures:
                future.result(timeout=20)
        copies = [path for path in folder.glob('daolook-*.db') if path != unrelated]
        self.assertEqual(len(copies), 2)
        self.assertEqual(unrelated.read_text(), 'keep')
        for path in copies:
            with closing(sqlite3.connect(path)) as connection:
                self.assertEqual(connection.execute('SELECT value FROM users').fetchone()[0], 'expected')

    def test_rotation_never_removes_source_with_a_snapshot_filename(self):
        folder = private_directory(self.root / 'backups')
        source = folder / 'daolook-20000101-000000-000000.db'
        shutil.copyfile(self.source, source)
        for _ in range(3):
            backup(source, folder, 1)
        self.assertTrue(source.is_file())
        self.assertEqual(len(list(folder.glob('daolook-*.db'))), 2)


if __name__ == '__main__':
    unittest.main()
