import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class RunSshCommandTests(unittest.TestCase):
    def test_local_mode_runs_command_without_import_error(self):
        from utils import run_ssh_command

        returncode, stdout, stderr = run_ssh_command(
            host="unused",
            user="unused",
            cmd="printf ok",
            local=True,
        )

        self.assertEqual(returncode, 0)
        self.assertEqual(stdout, "ok")
        self.assertEqual(stderr, "")


if __name__ == "__main__":
    unittest.main()
