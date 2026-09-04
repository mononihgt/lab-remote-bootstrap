import sys
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "lib"))


class FakeConfig:
    def __init__(self, data):
        self.data = data

    def get(self, key_path, default=None):
        value = self.data
        for key in key_path.split("."):
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value


def local_config():
    return FakeConfig(
        {
            "deployment": {"target": "local"},
            "cloud": {"host": "cloud.example.com", "user": "clouduser", "reverse_port": 2224},
        }
    )


def remote_config():
    return FakeConfig(
        {
            "deployment": {"target": "remote"},
            "target": {
                "host": "lab.example.com",
                "user": "labuser",
                "ssh_port": 2201,
                "ssh_identity_file": "~/.ssh/id_lab",
            },
            "cloud": {"host": "cloud.example.com", "user": "clouduser", "reverse_port": 2224},
        }
    )


class DeploymentContextTests(unittest.TestCase):
    def test_local_target_uses_active_login_not_cloud_user(self):
        from deployment import DeploymentContext

        with patch("deployment.getpass.getuser", return_value="labuser"):
            context = DeploymentContext.from_config(local_config())

        self.assertTrue(context.target.is_local)
        self.assertEqual(context.target.user, "labuser")
        self.assertEqual(
            context.reverse_tunnel_ssh_args(),
            ["ssh", "-p", "2224", "labuser@cloud.example.com"],
        )
        self.assertEqual(context.cloud_tunnel.user, "clouduser")

    def test_remote_target_never_falls_back_to_cloud_endpoint(self):
        from deployment import DeploymentConfigurationError, DeploymentContext

        config = remote_config()
        del config.data["target"]

        with self.assertRaisesRegex(DeploymentConfigurationError, "target.host"):
            DeploymentContext.from_config(config)

    def test_remote_target_routes_commands_over_its_own_ssh_endpoint(self):
        from deployment import DeploymentContext

        context = DeploymentContext.from_config(remote_config())
        with patch("deployment.run_ssh_command", return_value=(0, "ok", "")) as run_ssh:
            self.assertEqual(context.run("id -un"), (0, "ok", ""))

        run_ssh.assert_called_once_with(
            "lab.example.com", "labuser", "id -un", "~/.ssh/id_lab", 2201
        )
        self.assertEqual(
            context.target_ssh_args("-N"),
            ["ssh", "-N", "-i", os.path.expanduser("~/.ssh/id_lab"), "-p", "2201", "labuser@lab.example.com"],
        )

    def test_local_target_routes_commands_without_ssh(self):
        from deployment import DeploymentContext

        with patch("deployment.getpass.getuser", return_value="labuser"):
            context = DeploymentContext.from_config(local_config())
        with patch("deployment.run_command", return_value=(0, "ok", "")) as run_local:
            context.run("id -un")

        run_local.assert_called_once_with(
            ["bash", "-c", "id -un"], check=False, capture_output=True
        )

    def test_local_file_transfer_copies_without_scp(self):
        from deployment import DeploymentContext

        with patch("deployment.getpass.getuser", return_value="labuser"):
            context = DeploymentContext.from_config(local_config())
        with tempfile.TemporaryDirectory() as tempdir:
            source = Path(tempdir) / "source.txt"
            destination = Path(tempdir) / "target" / "destination.txt"
            source.write_text("deployment context")

            self.assertTrue(context.upload(str(source), str(destination)))
            self.assertEqual(destination.read_text(), "deployment context")

    def test_schema_requires_explicit_remote_target_fields(self):
        from config import Config, ConfigError

        content = """
deployment:
  mode: host
  target: remote
cloud:
  host: cloud.example.com
  user: clouduser
clash:
  install_root: /opt/lab-stack
autossh:
  identity_file: ~/.ssh/id_autossh
"""
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.yaml"
            config_path.write_text(content)
            with self.assertRaises(ConfigError):
                Config(str(config_path))

    def test_schema_rejects_removed_controller_identity_field(self):
        from config import Config, ConfigError

        content = """
deployment:
  mode: host
  target: local
  ssh_identity_file: ~/.ssh/old-key
cloud:
  host: cloud.example.com
  user: clouduser
clash:
  install_root: /opt/lab-stack
autossh:
  identity_file: ~/.ssh/id_autossh
"""
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "config.yaml"
            config_path.write_text(content)
            with self.assertRaises(ConfigError):
                Config(str(config_path))


if __name__ == "__main__":
    unittest.main()
