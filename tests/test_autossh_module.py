import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key_path, default=None):
        value = self.data
        for key in key_path.split("."):
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value


class AutoSSHModuleTests(unittest.TestCase):
    def test_cleanup_reverse_port_runs_on_cloud_through_lab_target(self):
        from modules.autossh_module import AutoSSHModule

        module = AutoSSHModule(
            FakeConfig(
                {
                    "cloud": {
                        "host": "cloud.example.com",
                        "user": "clouduser",
                        "reverse_port": 2222,
                    },
                    "autossh": {"identity_file": "~/.ssh/id_autossh"},
                }
            )
        )

        with patch("modules.autossh_module.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = (0, "", "")

            self.assertTrue(
                module._cleanup_reverse_port(
                    host="lab.example.com",
                    user="labuser",
                    control_identity_file="~/.ssh/id_lab",
                    port=22,
                    autossh_identity_file="~/.ssh/id_autossh",
                )
            )

        command = run_ssh_command.call_args.args[2]
        self.assertIn("ssh -i ~/.ssh/id_autossh", command)
        self.assertIn("clouduser@cloud.example.com", command)
        self.assertIn("fuser -k -n tcp 2222", command)
        self.assertIn("lsof -tiTCP:2222 -sTCP:LISTEN", command)

    def test_systemd_service_binds_reverse_port_to_configured_address(self):
        from modules.autossh_module import AutoSSHModule

        module = AutoSSHModule(
            FakeConfig(
                {
                    "cloud": {
                        "host": "cloud.example.com",
                        "user": "clouduser",
                        "reverse_port": 2222,
                        "reverse_bind_address": "0.0.0.0",
                    },
                    "autossh": {"identity_file": "~/.ssh/id_autossh"},
                }
            )
        )

        with patch("modules.autossh_module.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = (0, "", "")

            self.assertTrue(
                module._create_systemd_service(
                    host="lab.example.com",
                    user="labuser",
                    control_identity_file="~/.ssh/id_lab",
                    port=22,
                    monitor_port=20000,
                    autossh_identity_file="~/.ssh/id_autossh",
                )
            )

        service_command = run_ssh_command.call_args.args[2]
        self.assertIn("-R 0.0.0.0:2222:localhost:22", service_command)

    def test_start_service_fails_when_autossh_is_not_active(self):
        from modules.autossh_module import AutoSSHModule

        module = AutoSSHModule(FakeConfig())

        def run_ssh(_host, _user, cmd, _identity_file, _port):
            if cmd == "sudo systemctl restart lab-autossh.service":
                return 0, "", ""
            if cmd == "sudo systemctl is-active lab-autossh.service":
                return 3, "activating\n", ""
            raise AssertionError(f"unexpected command: {cmd}")

        with patch("modules.autossh_module.run_ssh_command", side_effect=run_ssh):
            self.assertFalse(module._start_service("host", "user", "id", 22))


if __name__ == "__main__":
    unittest.main()
