import sys
import unittest
from pathlib import Path
from unittest.mock import ANY, MagicMock


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

    @property
    def is_remote_deployment(self):
        return self.get("deployment.target") == "remote"


def remote_config():
    return FakeConfig(
        {
            "deployment": {"target": "remote"},
            "target": {"host": "lab.example.com", "user": "labuser", "ssh_port": 2201},
            "cloud": {"host": "cloud.example.com", "user": "clouduser"},
            "clash": {"install_root": "/opt/lab-stack"},
        }
    )


class SubscriptionStoreTests(unittest.TestCase):
    def test_live_remote_store_uses_deployment_context_for_sync(self):
        from subscription_store import SubscriptionStore

        store = SubscriptionStore(remote_config(), scope="live")
        context = MagicMock()
        context.run.return_value = (0, "", "")

        def download(_remote, local):
            Path(local).write_text('{"subscriptions": []}')
            return True

        context.download.side_effect = download
        context.upload.return_value = True
        store.context = context
        try:
            store.prepare()
            store.local_paths.config_file.write_text("mixed-port: 7890\n")
            store.sync(upload_config=True)
        finally:
            store.cleanup()

        self.assertEqual(context.run.call_args_list[0].args[0], "test -f /opt/lab-stack/clash/subscriptions.json")
        context.download.assert_called_once()
        context.upload.assert_any_call(
            ANY, "/opt/lab-stack/clash/subscriptions.json"
        )
        context.upload.assert_any_call(ANY, "/opt/lab-stack/clash/config.yaml")

    def test_workspace_scope_never_builds_remote_transport(self):
        from subscription_store import SubscriptionStore

        store = SubscriptionStore(remote_config(), scope="workspace")
        self.assertIsNone(store.context)
        self.assertEqual(store.prepare(), store)


if __name__ == "__main__":
    unittest.main()
