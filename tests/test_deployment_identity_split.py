import sys
import tempfile
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
    def is_local_deployment(self):
        return self.get("deployment.target") == "local"

    @property
    def is_remote_deployment(self):
        return self.get("deployment.target", "remote") == "remote"


def make_base_module(config):
    from modules import BaseModule

    class ConcreteModule(BaseModule):
        def validate(self):
            return True

        def deploy(self):
            return True

        def rollback(self):
            return True

    return ConcreteModule(config)


class DeploymentIdentitySplitTests(unittest.TestCase):
    def test_remote_deployment_uses_optional_control_ssh_identity(self):
        config = FakeConfig(
            {
                "deployment": {
                    "target": "remote",
                    "ssh_identity_file": "~/.ssh/id_ed25519",
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
                "autossh": {
                    "identity_file": "~/.ssh/id_ed25519_autossh",
                },
            }
        )

        module = make_base_module(config)

        self.assertEqual(
            module.get_deployment_params(),
            (
                "lab.example.com",
                "labuser",
                "~/.ssh/id_target",
                2222,
                False,
            ),
        )

    def test_remote_deployment_falls_back_to_old_control_ssh_fields(self):
        config = FakeConfig(
            {
                "deployment": {
                    "target": "remote",
                    "ssh_identity_file": "~/.ssh/id_ed25519",
                },
                "cloud": {
                    "host": "203.0.113.10",
                    "user": "clouduser",
                    "reverse_port": 2222,
                },
                "autossh": {
                    "identity_file": "~/.ssh/id_ed25519_autossh",
                },
            }
        )

        module = make_base_module(config)

        self.assertEqual(
            module.get_deployment_params(),
            ("203.0.113.10", "clouduser", "~/.ssh/id_ed25519", 2222, False),
        )

    def test_remote_deployment_does_not_reuse_autossh_identity_for_control_ssh(self):
        config = FakeConfig(
            {
                "deployment": {"target": "remote"},
                "target": {
                    "host": "lab.example.com",
                    "user": "labuser",
                    "ssh_port": 2222,
                },
                "cloud": {
                    "host": "203.0.113.10",
                    "user": "clouduser",
                    "reverse_port": 2223,
                },
                "autossh": {
                    "identity_file": "~/.ssh/id_ed25519_autossh",
                },
            }
        )

        module = make_base_module(config)

        self.assertEqual(
            module.get_deployment_params(),
            ("lab.example.com", "labuser", None, 2222, False),
        )

    def test_autossh_validation_does_not_require_server_side_key_on_local_machine(self):
        from modules.autossh_module import AutoSSHModule

        missing_key = "/definitely/not/on/this/local/machine/id_autossh"
        config = FakeConfig(
            {
                "deployment": {"target": "remote"},
                "cloud": {"host": "203.0.113.10", "user": "clouduser"},
                "autossh": {"identity_file": missing_key},
            }
        )

        module = AutoSSHModule(config)

        self.assertTrue(module.validate())

    def test_autossh_validation_checks_explicit_control_identity_when_configured(self):
        from modules.autossh_module import AutoSSHModule

        with tempfile.NamedTemporaryFile() as identity:
            config = FakeConfig(
                {
                    "deployment": {
                        "target": "remote",
                        "ssh_identity_file": identity.name,
                    },
                    "cloud": {"host": "203.0.113.10", "user": "clouduser"},
                    "autossh": {
                        "identity_file": "/server/side/id_autossh",
                    },
                }
            )

            module = AutoSSHModule(config)

            self.assertTrue(module.validate())

    def test_autossh_setup_references_server_side_key_without_uploading_it(self):
        from modules.autossh_module import AutoSSHModule

        config = FakeConfig(
            {
                "cloud": {"host": "203.0.113.10", "user": "clouduser"},
                "autossh": {"identity_file": "~/.ssh/id_ed25519_autossh"},
            }
        )
        module = AutoSSHModule(config)

        with patch("modules.autossh_module.run_ssh_command") as run_ssh_command:
            run_ssh_command.return_value = (0, "Connection successful\n", "")

            self.assertTrue(
                module._setup_ssh_key(
                    host="203.0.113.10",
                    user="clouduser",
                    control_identity_file=None,
                    port=2222,
                    autossh_identity_file="~/.ssh/id_ed25519_autossh",
                )
            )

        commands = [call.args[2] for call in run_ssh_command.call_args_list]
        self.assertFalse(any("scp" in command for command in commands))
        self.assertTrue(
            any(
                "ssh -i ~/.ssh/id_ed25519_autossh" in command
                for command in commands
            )
        )


if __name__ == "__main__":
    unittest.main()
