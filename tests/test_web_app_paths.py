import importlib.util
import sys
import unittest
from pathlib import Path as SysPath
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
    is_remote_deployment = True

    def get(self, key_path, default=None):
        values = {
            "clash.install_root": "/tmp/lab-web-runtime",
            "web.bind": "127.0.0.1",
            "clash.api_port": 9090,
        }
        return values.get(key_path, default)


class WebAppPathTests(unittest.TestCase):
    def test_web_app_uses_runtime_subscription_paths(self):
        app_path = PROJECT_ROOT / "web" / "app.py"
        spec = importlib.util.spec_from_file_location("web_app_paths_test", app_path)
        module = importlib.util.module_from_spec(spec)

        with patch("config.load_config", return_value=FakeConfig()):
            sys.modules["web_app_paths_test"] = module
            spec.loader.exec_module(module)

        self.assertEqual(module.subscriptions_file, "/tmp/lab-web-runtime/clash/subscriptions.json")
        self.assertEqual(module.config_file, "/tmp/lab-web-runtime/clash/config.yaml")

    def test_web_app_resolves_paths_with_web_runtime_context(self):
        app_path = PROJECT_ROOT / "web" / "app.py"
        spec = importlib.util.spec_from_file_location("web_app_paths_context_test", app_path)
        module = importlib.util.module_from_spec(spec)
        resolved_paths = type(
            "ResolvedPaths",
            (),
            {
                "subscriptions_file": SysPath("/tmp/resolved/subscriptions.json"),
                "config_file": SysPath("/tmp/resolved/config.yaml"),
            },
        )()

        with patch("config.load_config", return_value=FakeConfig()), \
             patch("subscription_paths.resolve_subscription_paths", return_value=resolved_paths) as resolve:
            sys.modules["web_app_paths_context_test"] = module
            spec.loader.exec_module(module)

        self.assertEqual(module.subscriptions_file, str(resolved_paths.subscriptions_file))
        self.assertEqual(module.config_file, str(resolved_paths.config_file))
        resolve.assert_called_once_with(
            unittest.mock.ANY,
            project_root=PROJECT_ROOT,
            runtime_context="web",
        )


if __name__ == "__main__":
    unittest.main()
