import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "lib"))


class FakeConfig:
    config_path = "/tmp/config.yaml"

    def __init__(self, data):
        self.data = data

    def get(self, key_path, default=None):
        value = self.data
        for key in key_path.split("."):
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return value

    @property
    def deployment_mode(self):
        return self.get("deployment.mode", "host")


def remote_config(target_port=2201):
    return FakeConfig(
        {
            "deployment": {"mode": "host", "target": "remote"},
            "target": {
                "host": "lab.example.com",
                "user": "labuser",
                "ssh_port": target_port,
                "ssh_identity_file": "~/.ssh/id_lab",
            },
            "cloud": {"host": "cloud.example.com", "user": "clouduser", "reverse_port": 2224},
        }
    )


class DeployerPreflightTests(unittest.TestCase):
    def test_remote_validation_checks_passwordless_sudo_on_target(self):
        from deployer import Deployer

        deployer = Deployer(remote_config())
        with patch("deployer.subprocess.run") as known_hosts, patch(
            "deployment.run_ssh_command", return_value=(1, "", "sudo: a password is required")
        ) as run_ssh:
            known_hosts.return_value = subprocess.CompletedProcess([], 0, "", "")
            self.assertFalse(deployer._validate_remote_sudo())

        run_ssh.assert_called_once_with(
            "lab.example.com", "labuser", "sudo -n true", "~/.ssh/id_lab", 2201
        )
        self.assertEqual(
            [call.args[0] for call in known_hosts.call_args_list],
            [["ssh-keygen", "-R", "lab.example.com"], ["ssh-keygen", "-R", "[lab.example.com]:2201"]],
        )

    def test_local_validation_prompts_with_sudo_v_without_ssh(self):
        from deployer import Deployer

        config = FakeConfig(
            {
                "deployment": {"mode": "host", "target": "local"},
                "cloud": {"host": "cloud.example.com", "user": "clouduser"},
            }
        )
        deployer = Deployer(config)
        with patch("deployer.os.geteuid", return_value=501), patch(
            "deployer.subprocess.run", return_value=subprocess.CompletedProcess(["sudo", "-v"], 0)
        ) as run:
            self.assertTrue(deployer._validate_remote_sudo())

        run.assert_called_once_with(["sudo", "-v"], check=False)

    def test_autossh_redeploy_rejects_the_active_reverse_tunnel_route(self):
        from deployer import Deployer

        config = remote_config(target_port=2224)
        config.data["target"]["host"] = "cloud.example.com"
        deployer = Deployer(config)

        self.assertFalse(deployer._validate_autossh_control_path(skip_autossh=False))

    def test_autossh_redeploy_allows_separate_maintenance_ssh_endpoint(self):
        from deployer import Deployer

        deployer = Deployer(remote_config())
        self.assertTrue(deployer._validate_autossh_control_path(skip_autossh=False))


if __name__ == "__main__":
    unittest.main()
