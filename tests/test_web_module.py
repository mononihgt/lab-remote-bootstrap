import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "lib"))


class FakeConfig:
    def get(self, key_path, default=None):
        values = {
            "deployment.target": "local",
            "cloud.host": "cloud.example.com",
            "cloud.user": "clouduser",
            "web.enabled": True,
        }
        return values.get(key_path, default)


class WebModuleTests(unittest.TestCase):
    def test_dependencies_create_a_persistent_python_312_venv(self):
        from modules.web_module import WebModule

        module = WebModule(FakeConfig())
        context = MagicMock()
        context.run.return_value = (0, "", "")
        module.context = context

        self.assertTrue(module._install_dependencies("/opt/lab-stack"))

        command = context.run.call_args.args[0]
        self.assertIn("uv venv --allow-existing --python 3.12 /opt/lab-stack/web/.venv", command)
        self.assertIn("uv pip install --python /opt/lab-stack/web/.venv/bin/python", command)

    def test_service_file_uses_resolved_target_user_and_venv_python(self):
        from modules.web_module import WebModule

        module = WebModule(FakeConfig())
        context = MagicMock()
        context.target.user = "coreknowledge"
        context.run.return_value = (0, "", "")
        module.context = context

        self.assertTrue(module._create_systemd_service("/opt/lab-stack"))

        command = context.run.call_args.args[0]
        self.assertIn("User=coreknowledge", command)
        self.assertIn("ExecStart=/opt/lab-stack/web/.venv/bin/python /opt/lab-stack/web/app.py", command)


if __name__ == "__main__":
    unittest.main()
