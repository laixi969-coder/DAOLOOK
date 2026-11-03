import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from server.config import instance_lock


class InstanceLockTests(unittest.TestCase):
    def test_second_process_is_rejected_until_lock_is_released(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'app.db'
            code = ('from server.config import instance_lock\n'
                    'import sys\n'
                    'with instance_lock(sys.argv[1]): print("acquired")\n')
            with instance_lock(database):
                attempt = subprocess.run([sys.executable, '-c', code, str(database)], capture_output=True, text=True)
                self.assertNotEqual(attempt.returncode, 0)
                self.assertIn('拒绝重复启动', attempt.stderr)
            attempt = subprocess.run([sys.executable, '-c', code, str(database)], capture_output=True, text=True)
            self.assertEqual(attempt.returncode, 0, attempt.stderr)
            self.assertIn('acquired', attempt.stdout)
