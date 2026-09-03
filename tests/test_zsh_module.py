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
    def test_install_tools_installs_and_verifies_zsh_before_optional_tools(self):
        from modules.zsh_module import ZshModule

        module = ZshModule(FakeConfig())

        def run_ssh(_host, _user, cmd, _identity_file, _port):
            if "then echo apt" in cmd:
                return 0, "apt\n", ""
            if cmd == "command -v zsh":
                return 0, "/usr/bin/zsh\n", ""
            return 0, "", ""

        with patch("modules.zsh_module.run_ssh_command", side_effect=run_ssh) as run_ssh_command:
            self.assertTrue(module._install_tools("host", "user", None, 22))

        commands = [call.args[2] for call in run_ssh_command.call_args_list]
        required_install = "sudo apt-get install -y zsh"
        self.assertIn(required_install, commands)
        self.assertIn("command -v zsh", commands)
        self.assertLess(commands.index(required_install), commands.index("command -v zsh"))

    def test_install_tools_fails_when_zsh_is_unavailable(self):
        from modules.zsh_module import ZshModule

        module = ZshModule(FakeConfig())

        def run_ssh(_host, _user, cmd, _identity_file, _port):
            if "then echo apt" in cmd:
                return 0, "apt\n", ""
            if cmd == "command -v zsh":
                return 1, "", "zsh not found"
            return 0, "", ""

        with patch("modules.zsh_module.run_ssh_command", side_effect=run_ssh):
            self.assertFalse(module._install_tools("host", "user", None, 22))

    def test_generated_config_runs_fastfetch_before_powerlevel10k(self):
        from modules.zsh_module import ZshModule

        module = ZshModule(FakeConfig())
        config_block = module._generate_config_block()

        fastfetch_index = config_block.index("# fastfetch")
        powerlevel_index = config_block.index("# powerlevel10k")

        self.assertLess(fastfetch_index, powerlevel_index)

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
