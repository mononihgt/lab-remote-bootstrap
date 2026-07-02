import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
    def __init__(self, remote=True, install_root="/tmp/lab-stack"):
        self.is_remote_deployment = remote
        self.install_root = install_root

    def get(self, key_path, default=None):
        if key_path == "clash.install_root":
            return self.install_root
        return default


class SubscriptionPathTests(unittest.TestCase):
    def test_cli_remote_context_uses_project_config_files(self):
        from subscription_paths import resolve_subscription_paths

        with tempfile.TemporaryDirectory() as root:
            project_root = Path(root)
            paths = resolve_subscription_paths(
                FakeConfig(remote=True, install_root="/opt/lab-remote-stack"),
                project_root=project_root,
                runtime_context="cli",
            )

        self.assertEqual(paths.subscriptions_file, project_root / "config" / "subscriptions.json")
        self.assertEqual(paths.config_file, project_root / "config" / "clash.generated.yaml")

    def test_cli_local_context_uses_install_root_files(self):
        from subscription_paths import resolve_subscription_paths

        paths = resolve_subscription_paths(
            FakeConfig(remote=False, install_root="/tmp/lab-stack"),
            project_root=PROJECT_ROOT,
            runtime_context="cli",
        )

        self.assertEqual(paths.subscriptions_file, Path("/tmp/lab-stack/clash/subscriptions.json"))
        self.assertEqual(paths.config_file, Path("/tmp/lab-stack/clash/config.yaml"))

    def test_web_context_uses_install_root_even_for_remote_deployment(self):
        from subscription_paths import resolve_subscription_paths

        paths = resolve_subscription_paths(
            FakeConfig(remote=True, install_root="/opt/lab-remote-stack"),
            project_root=PROJECT_ROOT,
            runtime_context="web",
        )

        self.assertEqual(paths.subscriptions_file, Path("/opt/lab-remote-stack/clash/subscriptions.json"))
        self.assertEqual(paths.config_file, Path("/opt/lab-remote-stack/clash/config.yaml"))

    def test_unknown_runtime_context_fails_fast(self):
        from subscription_paths import resolve_subscription_paths

        with self.assertRaisesRegex(ValueError, "Unknown subscription runtime context"):
            resolve_subscription_paths(FakeConfig(), runtime_context="worker")


if __name__ == "__main__":
    unittest.main()
