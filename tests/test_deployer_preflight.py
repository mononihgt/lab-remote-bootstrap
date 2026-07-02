import subprocess
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
    def make_remote_config(self):
        return FakeConfig(
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

    def test_remote_validation_fails_when_passwordless_sudo_is_unavailable(self):
        from deployer import Deployer

        deployer = Deployer(self.make_remote_config())

        with patch("deployer.subprocess.run") as run, patch("deployer.run_ssh_command") as run_ssh_command:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
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

    def test_remote_validation_cleans_target_known_hosts_before_sudo(self):
        from deployer import Deployer

        deployer = Deployer(self.make_remote_config())

        with patch("deployer.subprocess.run") as run, patch("deployer.run_ssh_command") as run_ssh_command:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            run_ssh_command.return_value = (0, "", "")

            self.assertTrue(
                deployer._validate_all(
                    skip_clash=True,
                    skip_autossh=True,
                    skip_zsh=True,
                    skip_web=True,
                )
            )

        self.assertEqual(
            [call.args[0] for call in run.call_args_list],
            [
                ["ssh-keygen", "-R", "203.0.113.10"],
                ["ssh-keygen", "-R", "[203.0.113.10]:2222"],
            ],
        )

    def test_local_validation_skips_known_hosts_cleanup(self):
        from deployer import Deployer

        config = FakeConfig(
            {
                "deployment": {"mode": "host", "target": "local"},
                "cloud": {"host": "203.0.113.10", "user": "clouduser"},
                "autossh": {"identity_file": "~/.ssh/id_ed25519_autossh"},
            }
        )
        deployer = Deployer(config)

        with patch("deployer.subprocess.run") as run:
            self.assertTrue(deployer._validate_remote_sudo())

        run.assert_not_called()

    def test_remote_validation_rejects_autossh_redeploy_through_same_reverse_port(self):
        from deployer import Deployer

        config = self.make_remote_config()
        config.data["target"]["ssh_port"] = 2223
        deployer = Deployer(config)

        with patch("deployer.subprocess.run") as run, patch("deployer.run_ssh_command") as run_ssh_command:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            run_ssh_command.return_value = (0, "", "")

            self.assertFalse(
                deployer._validate_all(
                    skip_clash=True,
                    skip_autossh=False,
                    skip_zsh=True,
                    skip_web=True,
                )
            )

        run_ssh_command.assert_not_called()

    def test_remote_validation_allows_same_reverse_port_when_autossh_is_skipped(self):
        from deployer import Deployer

        config = self.make_remote_config()
        config.data["target"]["ssh_port"] = 2223
        deployer = Deployer(config)

        with patch("deployer.subprocess.run") as run, patch("deployer.run_ssh_command") as run_ssh_command:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            run_ssh_command.return_value = (0, "", "")

            self.assertTrue(
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
            2223,
        )

    def test_remote_validation_allows_autossh_redeploy_through_separate_control_port(self):
        from deployer import Deployer

        config = self.make_remote_config()
        config.data["target"]["ssh_identity_file"] = None
        config.data["deployment"]["ssh_identity_file"] = None
        deployer = Deployer(config)

        with patch("deployer.subprocess.run") as run, patch("deployer.run_ssh_command") as run_ssh_command:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            run_ssh_command.return_value = (0, "", "")

            self.assertTrue(
                deployer._validate_all(
                    skip_clash=True,
                    skip_autossh=False,
                    skip_zsh=True,
                    skip_web=True,
                )
            )

        run_ssh_command.assert_called_once_with(
            "203.0.113.10",
            "labuser",
            "sudo -n true",
            None,
            2222,
        )

    def test_remote_validation_rejects_non_numeric_target_ssh_port_for_autossh(self):
        from deployer import Deployer

        config = self.make_remote_config()
        config.data["target"]["ssh_port"] = "not-a-port"
        deployer = Deployer(config)

        with patch("deployer.subprocess.run") as run, patch("deployer.run_ssh_command") as run_ssh_command:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            run_ssh_command.return_value = (0, "", "")

            self.assertFalse(
                deployer._validate_all(
                    skip_clash=True,
                    skip_autossh=False,
                    skip_zsh=True,
                    skip_web=True,
                )
            )

        run_ssh_command.assert_not_called()

    def test_remote_validation_leaves_missing_cloud_host_to_module_validation(self):
        from deployer import Deployer

        config = self.make_remote_config()
        config.data["target"]["host"] = None
        config.data["cloud"]["host"] = None
        config.data["target"]["ssh_port"] = 2223
        deployer = Deployer(config)

        with patch("deployer.subprocess.run") as run, patch("deployer.run_ssh_command") as run_ssh_command:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            run_ssh_command.return_value = (0, "", "")

            self.assertFalse(
                deployer._validate_all(
                    skip_clash=True,
                    skip_autossh=False,
                    skip_zsh=True,
                    skip_web=True,
                )
            )

        run_ssh_command.assert_called_once_with(
            None,
            "labuser",
            "sudo -n true",
            "~/.ssh/id_target",
            2223,
        )


if __name__ == "__main__":
    unittest.main()
