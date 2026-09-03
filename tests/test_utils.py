import sys
import unittest
from pathlib import Path
import tempfile
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

    def test_local_endpoint_does_not_spawn_ssh(self):
        from utils import run_ssh_command

        with patch("utils.getpass.getuser", return_value="unused"), \
             patch("utils.run_command", return_value=(0, "ok", "")) as run:
            self.assertEqual(
                run_ssh_command("localhost", "unused", "printf ok"),
                (0, "ok", ""),
            )
        run.assert_called_once_with(
            ["bash", "-c", "printf ok"],
            check=False,
            capture_output=True,
        )

    def test_local_endpoint_copies_files_without_scp(self):
        from utils import upload_file

        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "source.txt"
            destination = Path(tempdir) / "nested" / "destination.txt"
            source.write_text("content")

            with patch("utils.getpass.getuser", return_value="unused"):
                self.assertTrue(
                    upload_file(str(source), str(destination), "localhost", "unused")
                )
            self.assertEqual(destination.read_text(), "content")


if __name__ == "__main__":
    unittest.main()
