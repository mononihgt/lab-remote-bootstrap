import json
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = PROJECT_ROOT / "cli" / "lab-remote-ctl"
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


def load_cli_module():
    return SourceFileLoader("lab_remote_ctl_subscription_scope_tests", str(CLI_PATH)).load_module()


class FakeConfig:
    is_remote_deployment = True

    def get(self, key_path, default=None):
        return default


class FakeStore:
    seen_scopes = []

    def __init__(self, _config, scope="live"):
        self.seen_scopes.append(scope)
        self.tempdir = tempfile.TemporaryDirectory()
        temp_root = Path(self.tempdir.name)
        self.local_paths = type(
            "Paths",
            (),
            {
                "subscriptions_file": temp_root / "subscriptions.json",
                "config_file": temp_root / "config.yaml",
            },
        )()
        self.remote_paths = self.local_paths
        self.local_paths.subscriptions_file.write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "active": "Default",
                    "subscriptions": [
                        {
                            "name": "Default",
                            "url": "https://example.com/sub",
                            "type": None,
                            "template": "balanced",
                            "added_at": "2026-01-01T00:00:00Z",
                            "last_update": None,
                            "node_count": 0,
                            "status": "active",
                        }
                    ],
                }
            )
        )

    def prepare(self):
        return self

    def sync(self, upload_config=False):
        return None

    def cleanup(self):
        self.tempdir.cleanup()


class FailingPrepareStore:
    def __init__(self, _config, scope="live"):
        self.scope = scope

    def prepare(self):
        raise RuntimeError("remote unavailable")

    def cleanup(self):
        return None


class CliSubscriptionScopeTests(unittest.TestCase):
    def setUp(self):
        FakeStore.seen_scopes = []

    def test_subscription_list_defaults_to_live_scope(self):
        cli = load_cli_module()

        with patch.object(cli, "load_config", return_value=FakeConfig()), \
             patch("subscription_store.SubscriptionStore", FakeStore):
            result = CliRunner().invoke(cli.cli, ["subscription", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(FakeStore.seen_scopes, ["live"])
        self.assertIn("Subscriptions (live)", result.output)

    def test_subscription_list_accepts_workspace_scope(self):
        cli = load_cli_module()

        with patch.object(cli, "load_config", return_value=FakeConfig()), \
             patch("subscription_store.SubscriptionStore", FakeStore):
            result = CliRunner().invoke(
                cli.cli,
                ["subscription", "list", "--scope", "workspace"],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(FakeStore.seen_scopes, ["workspace"])
        self.assertIn("Subscriptions (workspace)", result.output)

    def test_subscription_list_reports_prepare_failures_without_traceback(self):
        cli = load_cli_module()

        with patch.object(cli, "load_config", return_value=FakeConfig()), \
             patch("subscription_store.SubscriptionStore", FailingPrepareStore):
            result = CliRunner().invoke(cli.cli, ["subscription", "list"])

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Failed to list subscriptions: remote unavailable", result.output)


if __name__ == "__main__":
    unittest.main()
