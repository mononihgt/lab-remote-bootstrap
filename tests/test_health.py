import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
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
    def is_remote_deployment(self):
        return self.get("deployment.target", "remote") == "remote"


def make_remote_config():
    return FakeConfig(
        {
            "deployment": {
                "target": "remote",
                "ssh_identity_file": "~/.ssh/id_legacy",
            },
            "target": {
                "host": "lab.example.com",
                "user": "labuser",
                "ssh_port": 2222,
                "ssh_identity_file": "~/.ssh/id_target",
            },
            "cloud": {
                "host": "203.0.113.10",
                "user": "clouduser",
                "reverse_port": 2223,
            },
            "clash": {
                "http_port": 7890,
                "socks_port": 7891,
                "api_port": 9090,
            },
        }
    )


class HealthCheckTests(unittest.TestCase):
    def test_remote_health_checks_services_and_ports_over_ssh(self):
        import health
        from health import HealthCheck

        remote_calls = []

        def fake_run_ssh_command(host, user, cmd, identity_file, port):
            remote_calls.append((host, user, cmd, identity_file, port))
            if cmd == "ps aux":
                return (
                    0,
                    "root 100 0.0 0.1 /opt/lab-remote-stack/clash/clash -d /opt/lab-remote-stack/clash\n"
                    "root 200 0.0 0.1 /usr/bin/autossh -M 0 cloud.example.com\n",
                    "",
                )
            if cmd == "ss -tlnp":
                return (
                    0,
                    "LISTEN 0 4096 0.0.0.0:7890 0.0.0.0:*\n"
                    "LISTEN 0 4096 0.0.0.0:7891 0.0.0.0:*\n"
                    "LISTEN 0 4096 127.0.0.1:9090 0.0.0.0:*\n",
                    "",
                )
            return 1, "", f"unexpected command: {cmd}"

        local_empty = subprocess.CompletedProcess([], 0, "", "")

        with patch.object(health, "run_ssh_command", side_effect=fake_run_ssh_command, create=True), \
             patch("health.subprocess.run", return_value=local_empty) as local_run:
            results = HealthCheck(make_remote_config()).run_all(check_connectivity=False)

        self.assertEqual(results["summary"]["failed"], 0)
        local_run.assert_not_called()
        self.assertTrue(remote_calls)
        self.assertTrue(all(call[0] == "lab.example.com" for call in remote_calls))
        self.assertTrue(all(call[1] == "labuser" for call in remote_calls))
        self.assertTrue(all(call[3] == "~/.ssh/id_target" for call in remote_calls))
        self.assertTrue(all(call[4] == 2222 for call in remote_calls))

    def test_remote_connectivity_checks_run_on_target_over_ssh(self):
        import health
        from health import HealthCheck

        remote_commands = []

        def fake_run_ssh_command(_host, _user, cmd, _identity_file, _port):
            remote_commands.append(cmd)
            if cmd == "ps aux":
                return (
                    0,
                    "root 100 0.0 0.1 /opt/lab-remote-stack/clash/clash -d /opt/lab-remote-stack/clash\n"
                    "root 200 0.0 0.1 /usr/bin/autossh -M 0 cloud.example.com\n",
                    "",
                )
            if cmd == "ss -tlnp":
                return (
                    0,
                    "LISTEN 0 4096 0.0.0.0:7890 0.0.0.0:*\n"
                    "LISTEN 0 4096 0.0.0.0:7891 0.0.0.0:*\n"
                    "LISTEN 0 4096 127.0.0.1:9090 0.0.0.0:*\n",
                    "",
                )
            if "127.0.0.1:9090/version" in cmd:
                return 0, "v1.19.0\n", ""
            if "www.gstatic.com/generate_204" in cmd:
                return 0, "204\n", ""
            return 1, "", f"unexpected command: {cmd}"

        with patch.object(health, "run_ssh_command", side_effect=fake_run_ssh_command, create=True), \
             patch("health.requests.get") as requests_get:
            results = HealthCheck(make_remote_config()).run_all(check_connectivity=True)

        requests_get.assert_not_called()
        self.assertEqual(results["summary"]["failed"], 0)
        self.assertTrue(any("127.0.0.1:9090/version" in cmd for cmd in remote_commands))
        self.assertTrue(any("www.gstatic.com/generate_204" in cmd for cmd in remote_commands))

    def test_target_runtime_context_checks_remote_config_locally(self):
        import health
        from health import HealthCheck

        def fake_local_run(cmd, capture_output, text, timeout):
            if cmd == ["ps", "aux"]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "root 100 0.0 0.1 /opt/lab-remote-stack/clash/clash -d /opt/lab-remote-stack/clash\n"
                    "root 200 0.0 0.1 /usr/bin/autossh -M 0 cloud.example.com\n",
                    "",
                )
            if cmd == ["ss", "-tlnp"]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    "LISTEN 0 4096 0.0.0.0:7890 0.0.0.0:*\n"
                    "LISTEN 0 4096 0.0.0.0:7891 0.0.0.0:*\n"
                    "LISTEN 0 4096 127.0.0.1:9090 0.0.0.0:*\n",
                    "",
                )
            return subprocess.CompletedProcess(cmd, 1, "", f"unexpected command: {cmd}")

        with patch.object(health, "run_ssh_command", side_effect=AssertionError("should not use SSH")), \
             patch("health.subprocess.run", side_effect=fake_local_run):
            results = HealthCheck(make_remote_config(), runtime_context="target").run_all(check_connectivity=False)

        self.assertEqual(results["summary"]["failed"], 0)


if __name__ == "__main__":
    unittest.main()
