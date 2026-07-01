import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
    config_path = "/tmp/config.yaml"

    def __init__(self, data):
        self.data = data

    def get(self, key_path, default=None):
        value = self.data
        for key in key_path.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    @property
    def is_local_deployment(self):
        return self.get("deployment.target") == "local"

    @property
    def is_remote_deployment(self):
        return self.get("deployment.target", "remote") == "remote"

    @property
    def deployment_mode(self):
        return self.get("deployment.mode", "host")


class DeployerPreflightTests(unittest.TestCase):
    def test_remote_validation_fails_when_passwordless_sudo_is_unavailable(self):
        from deployer import Deployer

        config = FakeConfig(
            {
                "deployment": {
                    "mode": "host",
                    "target": "remote",
                    "ssh_identity_file": "~/.ssh/id_target",
                },
                "target": {
                    "host": "203.0.113.10",
                    "user": "labuser",
                    "ssh_port": 2222,
                    "ssh_identity_file": "~/.ssh/id_target",
                },
                "cloud": {
                    "host": "203.0.113.10",
                    "user": "clouduser",
                    "reverse_port": 2223,
                },
                "autossh": {"identity_file": "~/.ssh/id_ed25519_autossh"},
            }
        )
        deployer = Deployer(config)

        with patch("deployer.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = (1, "", "sudo: a password is required")

            self.assertFalse(
                deployer._validate_all(
                    skip_clash=True,
                    skip_autossh=True,
                    skip_zsh=True,
                    skip_web=True,
                )
            )

        run_ssh_command.assert_called_once_with(
            "203.0.113.10",
            "labuser",
            "sudo -n true",
            "~/.ssh/id_target",
            2222,
        )


if __name__ == "__main__":
    unittest.main()
