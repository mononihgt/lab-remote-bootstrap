import json
import sys
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_ROOT / "cli" / "lab-remote-ctl"


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


if __name__ == "__main__":
    unittest.main()
