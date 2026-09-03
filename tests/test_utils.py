import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class RunSshCommandTests(unittest.TestCase):
    def test_supported_python_version(self):
        from utils import check_python_version

        supported, details = check_python_version((3, 12, 1))

        self.assertTrue(supported)
        self.assertEqual(details, "3.12.1")

    def test_unsupported_python_version_has_interpreter_remediation(self):
        from utils import check_python_version

        supported, details = check_python_version((3, 6, 9))

        self.assertFalse(supported)
        self.assertIn("Python 3.6.9 is not supported", details)
        self.assertIn("python3.12 -m pip install -r requirements.txt", details)

    def test_remote_ssh_command_builds_secure_ssh_invocation(self):
        from utils import run_ssh_command

        with patch("utils.run_command", return_value=(0, "ok", "")) as run:
            self.assertEqual(run_ssh_command("lab.example.com", "labuser", "printf ok"), (0, "ok", ""))
        run.assert_called_once_with(
            [
                "ssh",
                "-p",
                "22",
                "-o",
                "StrictHostKeyChecking=accept-new",
                "-o",
                "ConnectTimeout=10",
                "labuser@lab.example.com",
                "printf ok",
            ],
            check=False,
            capture_output=True,
        )


if __name__ == "__main__":
    unittest.main()
