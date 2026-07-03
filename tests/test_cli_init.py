import json
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_ROOT / "cli" / "lab-remote-ctl"
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


def load_cli_module():
    return SourceFileLoader("lab_remote_ctl_for_tests", str(CLI_PATH)).load_module()


class InitConfigGenerationTests(unittest.TestCase):
    def test_remote_config_separates_target_and_cloud_sections(self):
        cli = load_cli_module()

        content = cli.build_config_content(
            mode="host",
            deployment_target="remote",
            target_host="203.0.113.10",
            target_user="labuser",
            target_ssh_port=2222,
            target_ssh_identity_file="~/.ssh/id_target",
            cloud_host="203.0.113.10",
            cloud_user="clouduser",
            reverse_port=2222,
            clash_http=7890,
            clash_socks=7891,
            clash_api=9090,
            autossh_identity_file="~/.ssh/id_ed25519_autossh",
        )
        data = yaml.safe_load(content)

        self.assertEqual(data["target"]["user"], "labuser")
        self.assertEqual(data["target"]["ssh_identity_file"], "~/.ssh/id_target")
        self.assertEqual(data["cloud"]["user"], "clouduser")
        self.assertEqual(data["cloud"]["reverse_port"], 2222)
        self.assertNotIn("ssh_identity_file", data["deployment"])

    def test_subscription_seed_json_contains_default_subscription(self):
        cli = load_cli_module()

        content = cli.build_subscriptions_content(
            subscription_url="https://example.com/sub",
            template="balanced",
        )
        data = json.loads(content)

        self.assertEqual(data["active"], "Default")
        self.assertEqual(data["subscriptions"][0]["name"], "Default")
        self.assertEqual(data["subscriptions"][0]["url"], "https://example.com/sub")
        self.assertEqual(data["subscriptions"][0]["template"], "balanced")
        self.assertEqual(data["subscriptions"][0]["status"], "active")

    def test_empty_subscription_url_skips_seed_json(self):
        cli = load_cli_module()

        self.assertIsNone(cli.build_subscriptions_content("", "balanced"))

    def test_default_subscription_paths_use_live_install_root(self):
        cli = load_cli_module()
        from subscription_paths import resolve_subscription_paths

        class Config:
            is_remote_deployment = True

            def get(self, key_path, default=None):
                return default

        paths = resolve_subscription_paths(Config())

        self.assertEqual(paths.subscriptions_file, Path("/opt/lab-remote-stack/clash/subscriptions.json"))
        self.assertEqual(paths.config_file, Path("/opt/lab-remote-stack/clash/config.yaml"))

    def test_workspace_subscription_paths_use_project_config_directory(self):
        cli = load_cli_module()
        from subscription_paths import resolve_subscription_paths

        class Config:
            is_remote_deployment = True

            def get(self, key_path, default=None):
                return default

        paths = resolve_subscription_paths(Config(), scope="workspace")

        self.assertEqual(paths.subscriptions_file, PROJECT_ROOT / "config" / "subscriptions.json")
        self.assertEqual(paths.config_file, PROJECT_ROOT / "config" / "clash.generated.yaml")

    def test_local_subscription_paths_use_install_root(self):
        cli = load_cli_module()
        from subscription_paths import resolve_subscription_paths

        class Config:
            is_remote_deployment = False

            def get(self, key_path, default=None):
                if key_path == "clash.install_root":
                    return "/tmp/lab-stack"
                return default

        paths = resolve_subscription_paths(Config())

        self.assertEqual(paths.subscriptions_file, Path("/tmp/lab-stack/clash/subscriptions.json"))
        self.assertEqual(paths.config_file, Path("/tmp/lab-stack/clash/config.yaml"))

    def test_remote_web_access_uses_local_tunnel_instructions(self):
        cli = load_cli_module()

        class Config:
            is_remote_deployment = True

            def get(self, key_path, default=None):
                values = {
                    "target.host": "203.0.113.10",
                    "target.user": "labuser",
                    "target.ssh_port": 2222,
                    "target.ssh_identity_file": "~/.ssh/id_target",
                    "web.port": 5000,
                    "clash.api_port": 9090,
                }
                return values.get(key_path, default)

        access = cli.resolve_web_access(Config())

        self.assertEqual(access.url, "http://localhost:5001")
        self.assertEqual(
            access.tunnel_command,
            "ssh -N -L 5001:127.0.0.1:5000 -L 9090:127.0.0.1:9090 "
            "-i ~/.ssh/id_target -p 2222 labuser@203.0.113.10",
        )
        self.assertEqual(
            access.tunnel_args,
            [
                "ssh",
                "-fN",
                "-o",
                "ExitOnForwardFailure=yes",
                "-L",
                "5001:127.0.0.1:5000",
                "-L",
                "9090:127.0.0.1:9090",
                "-i",
                "~/.ssh/id_target",
                "-p",
                "2222",
                "labuser@203.0.113.10",
            ],
        )

    def test_local_web_access_uses_configured_port(self):
        cli = load_cli_module()

        class Config:
            is_remote_deployment = False

            def get(self, key_path, default=None):
                if key_path == "web.port":
                    return 5000
                return default

        access = cli.resolve_web_access(Config())

        self.assertEqual(access.url, "http://localhost:5000")
        self.assertIsNone(access.tunnel_command)
        self.assertIsNone(access.tunnel_args)

    def test_ensure_web_tunnel_starts_remote_tunnel_when_missing(self):
        cli = load_cli_module()

        access = cli.WebAccess(
            url="http://localhost:5001",
            tunnel_command="ssh -N -L 5001:127.0.0.1:5000 host",
            tunnel_args=["ssh", "-fN", "-L", "5001:127.0.0.1:5000", "host"],
            local_web_port=5001,
        )

        with patch.object(cli, "is_local_port_listening", return_value=False), \
             patch.object(cli.subprocess, "run") as run:
            run.return_value.returncode = 0

            self.assertTrue(cli.ensure_web_tunnel(access))

        run.assert_called_once_with(
            ["ssh", "-fN", "-L", "5001:127.0.0.1:5000", "host"],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_ensure_web_tunnel_reuses_existing_listener(self):
        cli = load_cli_module()

        access = cli.WebAccess(
            url="http://localhost:5001",
            tunnel_command="ssh -N -L 5001:127.0.0.1:5000 host",
            tunnel_args=["ssh", "-fN", "-L", "5001:127.0.0.1:5000", "host"],
            local_web_port=5001,
        )

        with patch.object(cli, "is_local_port_listening", return_value=True), \
             patch.object(cli.subprocess, "run") as run:
            self.assertTrue(cli.ensure_web_tunnel(access))

        run.assert_not_called()

    def test_stop_web_tunnel_kills_local_listener_for_remote_access(self):
        cli = load_cli_module()

        access = cli.WebAccess(
            url="http://localhost:5001",
            tunnel_command="ssh -N -L 5001:127.0.0.1:5000 host",
            tunnel_args=["ssh", "-fN", "-L", "5001:127.0.0.1:5000", "host"],
            local_web_port=5001,
        )

        with patch.object(cli.subprocess, "run") as run:
            run.return_value.returncode = 0

            self.assertTrue(cli.stop_web_tunnel(access))

        command = run.call_args.args[0]
        self.assertEqual(command[:2], ["sh", "-c"])
        self.assertIn("lsof -tiTCP:5001 -sTCP:LISTEN", command[2])


if __name__ == "__main__":
    unittest.main()
