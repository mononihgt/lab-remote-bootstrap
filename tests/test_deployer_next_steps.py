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


class DeployerNextStepsTests(unittest.TestCase):
    def make_config(self):
        return FakeConfig(
            {
                "deployment": {"mode": "host", "target": "remote"},
                "cloud": {
                    "host": "cloud.example.com",
                    "user": "clouduser",
                    "reverse_port": 2223,
                },
                "target": {"user": "labuser"},
                "clash": {
                    "mixed_port": 7890,
                    "external_controller": "127.0.0.1:9090",
                },
                "web": {"port": 8080},
            }
        )

    def capture_next_steps(self, deployed_modules, skipped_modules=None, failed_modules=None):
        from deployer import Deployer

        deployer = Deployer(self.make_config())
        messages = []
        with patch("deployer.print_info", side_effect=messages.append):
            deployer._print_next_steps(
                deployed_modules=deployed_modules,
                skipped_modules=skipped_modules or [],
                failed_modules=failed_modules or [],
            )
        return "\n".join(messages)

    def test_prints_next_steps_for_successfully_deployed_modules(self):
        output = self.capture_next_steps(["clash", "autossh", "zsh", "web"])

        self.assertIn("ssh -p 2223 labuser@cloud.example.com", output)
        self.assertIn("lab-remote-ctl subscription add", output)
        self.assertIn("Clash local proxy: 127.0.0.1:7890", output)
        self.assertIn("Clash controller: http://127.0.0.1:9090", output)
        self.assertIn("ssh -N -L 5001:127.0.0.1:8080 -L 9090:127.0.0.1:9090", output)
        self.assertIn("Web management UI: http://localhost:5001", output)
        self.assertIn("Start a new shell session", output)
        self.assertIn("lab-remote-ctl health", output)

    def test_omits_steps_for_skipped_modules(self):
        output = self.capture_next_steps(
            deployed_modules=["autossh"],
            skipped_modules=["clash", "zsh", "web"],
        )

        self.assertIn("ssh -p 2223 labuser@cloud.example.com", output)
        self.assertNotIn("subscription add", output)
        self.assertNotIn("Clash local proxy", output)
        self.assertNotIn("Web management UI", output)
        self.assertNotIn("Start a new shell session", output)
        self.assertIn("Skipped this run: clash, zsh, web", output)

    def test_prioritizes_non_critical_failures_over_module_steps(self):
        output = self.capture_next_steps(
            deployed_modules=["clash", "autossh"],
            failed_modules=["web", "zsh"],
        )

        self.assertIn("Review failed non-critical modules: web, zsh", output)
        self.assertIn("Re-run deploy for those modules after fixing the errors", output)
        self.assertIn("ssh -p 2223 labuser@cloud.example.com", output)
        self.assertIn("lab-remote-ctl subscription add", output)
        self.assertNotIn("Web management UI", output)
        self.assertNotIn("Start a new shell session", output)


if __name__ == "__main__":
    unittest.main()
