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
        }
        return values.get(key_path, default)


class ClashModuleTests(unittest.TestCase):
    def test_service_file_uses_resolved_target_user(self):
        from modules.clash_module import ClashModule

        module = ClashModule(FakeConfig())
        context = MagicMock()
        context.target.user = "coreknowledge"
        context.run.return_value = (0, "", "")
        module.context = context

        self.assertTrue(module._create_systemd_service("/opt/lab-stack"))

        command = context.run.call_args.args[0]
        self.assertIn("User=coreknowledge", command)
        self.assertNotIn("clouduser", command)


if __name__ == "__main__":
    unittest.main()
