import subprocess
import sys
import unittest
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


def remote_config():
    return FakeConfig(
        {
            "deployment": {"target": "remote"},
            "target": {"host": "lab.example.com", "user": "labuser", "ssh_port": 2201},
            "cloud": {"host": "cloud.example.com", "user": "clouduser"},
            "clash": {"http_port": 7890, "socks_port": 7891, "api_port": 9090},
        }
    )


class HealthCheckTests(unittest.TestCase):
    def test_controller_health_checks_execute_on_remote_target(self):
        from health import HealthCheck

        def remote_run(_host, _user, command, _identity, _port):
            if command.startswith("ps aux"):
                return 0, "lab 100 0 0 autossh\nlab 101 0 0 mihomo\n", ""
            if command.startswith("ss "):
                return 0, "LISTEN 0 4096 127.0.0.1:7890\n127.0.0.1:7891\n127.0.0.1:9090\n", ""
            raise AssertionError(command)

        with patch("deployment.run_ssh_command", side_effect=remote_run) as run_ssh:
            results = HealthCheck(remote_config()).run_all(check_connectivity=False)

        self.assertEqual(results["summary"]["failed"], 0)
        self.assertTrue(all(call.args[0] == "lab.example.com" for call in run_ssh.call_args_list))
        self.assertTrue(all(call.args[1] == "labuser" for call in run_ssh.call_args_list))

    def test_target_runtime_never_sshes_back_to_configured_target(self):
        from health import HealthCheck

        def local_run(command, **_kwargs):
            if command == ["ps", "aux"]:
                return subprocess.CompletedProcess(command, 0, "lab 100 0 0 autossh\nlab 101 0 0 mihomo\n", "")
            if command == ["ss", "-tlnp"]:
                return subprocess.CompletedProcess(command, 0, "127.0.0.1:7890 7891 9090", "")
            raise AssertionError(command)

        with patch("health.subprocess.run", side_effect=local_run), patch(
            "deployment.run_ssh_command", side_effect=AssertionError("unexpected SSH")
        ):
            results = HealthCheck(remote_config(), runtime_context="target").run_all(
                check_connectivity=False
            )

        self.assertEqual(results["summary"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
