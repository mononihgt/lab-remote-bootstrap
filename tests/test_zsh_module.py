import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "lib"))


class FakeConfig:
    def get(self, key_path, default=None):
        values = {
            "deployment.target": "local",
            "cloud.host": "cloud.example.com",
            "cloud.user": "clouduser",
            "clash.http_port": 7890,
            "clash.socks_port": 7891,
            "clash.api_port": 9090,
            "zsh.custom_config": {},
        }
        return values.get(key_path, default)


class ZshModuleTests(unittest.TestCase):
    def test_installs_zsh_as_required_tool_and_optional_enhancements(self):
        from modules.zsh_module import ZshModule

        module = ZshModule(FakeConfig())
        context = MagicMock()
        context.run.side_effect = [(0, "apt\n", ""), (0, "", ""), (0, "/usr/bin/zsh\n", "")] + [(0, "", "")] * 6
        module.context = context

        self.assertTrue(module._install_tools())

        commands = [call.args[0] for call in context.run.call_args_list]
        self.assertIn("sudo apt-get install -y zsh", commands)
        self.assertIn("command -v zsh", commands)

    def test_generated_configuration_sets_proxy_ports(self):
        from modules.zsh_module import ZshModule

        config_block = ZshModule(FakeConfig())._generate_config_block()

        self.assertIn('export http_proxy="http://127.0.0.1:7890"', config_block)
        self.assertIn('export all_proxy="socks5://127.0.0.1:7891"', config_block)


if __name__ == "__main__":
    unittest.main()
