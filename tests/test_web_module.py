import sys
import tempfile
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


class WebModuleTests(unittest.TestCase):
    def test_upload_web_app_copies_runtime_lib_modules(self):
        from modules.web_module import WebModule

        with tempfile.TemporaryDirectory() as project_root:
            root = Path(project_root)
            web_dir = root / "web"
            lib_dir = root / "lib"
            web_dir.mkdir()
            lib_dir.mkdir()
            (web_dir / "app.py").write_text("print('web')\n")
            for name in ["config.py", "subscription.py", "subscription_paths.py", "health.py", "utils.py"]:
                (lib_dir / name).write_text(f"# {name}\n")

            module = WebModule(FakeConfig())

            with patch("modules.web_module.get_project_root", return_value=root), \
                 patch("modules.web_module.upload_file", return_value=True) as upload:
                self.assertTrue(
                    module._upload_web_app("host", "user", "id", 2222, "/opt/lab-remote-stack")
                )

            self.assertEqual(
                [call.args[1] for call in upload.call_args_list],
                [
                    "/opt/lab-remote-stack/web/app.py",
                    "/opt/lab-remote-stack/lib/config.py",
                    "/opt/lab-remote-stack/lib/subscription.py",
                    "/opt/lab-remote-stack/lib/subscription_paths.py",
                    "/opt/lab-remote-stack/lib/health.py",
                    "/opt/lab-remote-stack/lib/utils.py",
                ],
            )

    def test_start_service_fails_when_systemd_service_is_not_active(self):
        from modules.web_module import WebModule

        module = WebModule(FakeConfig())

        def run_ssh(_host, _user, cmd, _identity_file, _port):
            if cmd == "sudo systemctl start lab-web.service":
                return 0, "", ""
            if cmd == "sudo systemctl is-active lab-web.service":
                return 3, "activating\n", ""
            raise AssertionError(f"unexpected command: {cmd}")

        with patch("modules.web_module.run_ssh_command", side_effect=run_ssh):
            self.assertFalse(module._start_service("host", "user", "id", 2222))


if __name__ == "__main__":
    unittest.main()
