import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key_path, default=None):
        value = self.data
        for key in key_path.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value


class ZshModuleTests(unittest.TestCase):
    def test_write_config_writes_managed_block_to_home_zshrc(self):
        from modules.zsh_module import ZshModule

        module = ZshModule(FakeConfig())
        config_block = "# >>> lab-remote-bootstrap >>>\nexport TEST_VALUE='ok'\n# <<< lab-remote-bootstrap <<<\n"

        with tempfile.TemporaryDirectory() as home:
            zshrc = Path(home) / ".zshrc"
            zshrc.write_text("alias existing='true'\n")

            def run_locally(_host, _user, cmd, _identity_file, _port):
                env = os.environ.copy()
                env["HOME"] = home
                result = subprocess.run(
                    ["bash", "-c", cmd],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=env,
                )
                return result.returncode, result.stdout, result.stderr

            with patch("modules.zsh_module.run_ssh_command", side_effect=run_locally):
                self.assertTrue(module._write_config("host", "user", None, 22, config_block))

            self.assertEqual(
                zshrc.read_text(),
                "alias existing='true'\n# >>> lab-remote-bootstrap >>>\n"
                "export TEST_VALUE='ok'\n"
                "# <<< lab-remote-bootstrap <<<\n",
            )


if __name__ == "__main__":
    unittest.main()
