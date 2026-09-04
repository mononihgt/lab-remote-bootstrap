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
            "cloud.reverse_port": 2224,
            "cloud.reverse_bind_address": "0.0.0.0",
            "autossh.identity_file": "~/.ssh/id_autossh",
            "autossh.monitor_port": 20000,
        }
        return values.get(key_path, default)


class AutoSSHModuleTests(unittest.TestCase):
    def test_service_uses_target_account_locally_and_cloud_account_outbound(self):
        from modules.autossh_module import AutoSSHModule

        module = AutoSSHModule(FakeConfig())
        context = MagicMock()
        context.target.user = "labuser"
        context.cloud_tunnel.host = "cloud.example.com"
        context.cloud_tunnel.user = "clouduser"
        context.cloud_tunnel.reverse_port = 2224
        context.cloud_tunnel.reverse_bind_address = "0.0.0.0"
        context.run.return_value = (0, "", "")
        module.context = context

        self.assertTrue(module._create_systemd_service(20000, "~/.ssh/id_autossh"))

        command = context.run.call_args.args[0]
        self.assertIn("User=labuser", command)
        self.assertIn("-R 0.0.0.0:2224:localhost:22", command)
        self.assertIn("clouduser@cloud.example.com", command)
        self.assertIn("-i %h/.ssh/id_autossh", command)
        self.assertNotIn("User=clouduser", command)

    def test_validation_requires_only_server_side_autossh_identity(self):
        from modules.autossh_module import AutoSSHModule

        module = AutoSSHModule(FakeConfig())
        self.assertTrue(module.validate())

    def test_setup_ssh_key_expands_home_relative_identity_path(self):
        from modules.autossh_module import AutoSSHModule

        module = AutoSSHModule(FakeConfig())
        context = MagicMock()
        context.cloud_tunnel.host = "cloud.example.com"
        context.cloud_tunnel.user = "clouduser"
        context.run.return_value = (0, "", "")
        module.context = context

        self.assertTrue(module._setup_ssh_key("~/.ssh/id_rsa"))

        commands = [call.args[0] for call in context.run.call_args_list]
        self.assertIn('chmod 600 "$HOME"/.ssh/id_rsa', commands)
        self.assertNotIn("'~/.ssh/id_rsa'", "\n".join(commands))


if __name__ == "__main__":
    unittest.main()
