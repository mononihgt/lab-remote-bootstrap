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


class DeployerNextStepsTests(unittest.TestCase):
    def capture(self, config, modules):
        from deployer import Deployer

        messages = []
        with patch("deployer.print_info", side_effect=messages.append):
            Deployer(config)._print_next_steps(deployed_modules=modules)
        return "\n".join(messages)

    def test_local_reverse_tunnel_uses_local_lab_account(self):
        config = FakeConfig(
            {
                "deployment": {"mode": "host", "target": "local"},
                "cloud": {
                    "host": "cloud.example.com",
                    "user": "clouduser",
                    "reverse_port": 2224,
                },
            }
        )
        with patch("deployment.getpass.getuser", return_value="labuser"):
            output = self.capture(config, ["autossh"])

        self.assertIn("ssh -p 2224 labuser@cloud.example.com", output)
        self.assertNotIn("clouduser@cloud.example.com", output)

    def test_remote_web_tunnel_uses_target_not_cloud_identity(self):
        config = FakeConfig(
            {
                "deployment": {"mode": "host", "target": "remote"},
                "target": {"host": "lab.example.com", "user": "labuser", "ssh_port": 2201},
                "cloud": {"host": "cloud.example.com", "user": "clouduser", "reverse_port": 2224},
                "web": {"port": 5000, "local_port": 5001},
                "clash": {"api_port": 9090},
            }
        )
        output = self.capture(config, ["autossh", "web"])

        self.assertIn("ssh -p 2224 labuser@cloud.example.com", output)
        self.assertIn("ssh -N -L 5001:127.0.0.1:5000", output)
        self.assertIn("-p 2201 labuser@lab.example.com", output)
        self.assertNotIn("clouduser@lab.example.com", output)


if __name__ == "__main__":
    unittest.main()
