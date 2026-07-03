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

    @property
    def is_local_deployment(self):
        return self.get("deployment.target") == "local"


class ClashModuleTests(unittest.TestCase):
    def test_upload_clash_binary_promotes_uploaded_temp_file(self):
        from modules.clash_module import ClashModule

        with tempfile.TemporaryDirectory() as project_root:
            clash_assets = Path(project_root) / "assets" / "clash"
            clash_assets.mkdir(parents=True)
            local_binary = clash_assets / "mihomo-linux-amd64"
            local_binary.write_bytes(b"binary")

            module = ClashModule(FakeConfig())

            with patch("modules.clash_module.get_project_root", return_value=Path(project_root)), \
                 patch("modules.clash_module.upload_file", return_value=True) as upload, \
                 patch("modules.clash_module.run_ssh_command", return_value=(0, "", "")) as run_ssh:
                self.assertTrue(
                    module._upload_clash_binary("host", "user", "id", 2222, "/opt/lab-remote-stack")
                )

        upload.assert_called_once_with(
            str(local_binary),
            "/opt/lab-remote-stack/clash/clash.upload",
            "host",
            "user",
            "id",
            2222,
        )
        run_ssh.assert_called_once_with(
            "host",
            "user",
            "mv -f /opt/lab-remote-stack/clash/clash.upload /opt/lab-remote-stack/clash/clash && chmod +x /opt/lab-remote-stack/clash/clash",
            "id",
            2222,
        )

    def test_start_service_restarts_existing_clash_service(self):
        from modules.clash_module import ClashModule

        module = ClashModule(FakeConfig())

        with patch("modules.clash_module.run_ssh_command") as run_ssh, \
             patch("time.sleep"):
            run_ssh.side_effect = [
                (0, "", ""),
                (0, "active\n", ""),
            ]

            self.assertTrue(module._start_service("host", "user", "id", 2222))

        self.assertEqual(
            run_ssh.call_args_list[0].args,
            ("host", "user", "sudo systemctl restart lab-clash.service", "id", 2222),
        )

    def test_upload_subscription_files_copies_seed_and_generated_config_when_present(self):
        from modules.clash_module import ClashModule

        with tempfile.TemporaryDirectory() as project_root:
            config_dir = Path(project_root) / "config"
            config_dir.mkdir()
            subscriptions = config_dir / "subscriptions.json"
            generated_config = config_dir / "clash.generated.yaml"
            subscriptions.write_text('{"subscriptions": []}')
            generated_config.write_text("mixed-port: 7890\n")

            module = ClashModule(FakeConfig())

            with patch("modules.clash_module.get_project_root", return_value=Path(project_root)), \
                 patch("modules.clash_module.upload_file", return_value=True) as upload:
                self.assertTrue(
                    module._upload_subscription_files("host", "user", "id", 2222, "/opt/lab-remote-stack")
                )

            self.assertEqual(
                [call.args[1] for call in upload.call_args_list],
                [
                    "/opt/lab-remote-stack/clash/subscriptions.json",
                    "/opt/lab-remote-stack/clash/config.yaml",
                ],
            )

    def test_upload_subscription_files_skips_missing_files(self):
        from modules.clash_module import ClashModule

        with tempfile.TemporaryDirectory() as project_root:
            module = ClashModule(FakeConfig())

            with patch("modules.clash_module.get_project_root", return_value=Path(project_root)), \
                 patch("modules.clash_module.upload_file") as upload:
                self.assertTrue(
                    module._upload_subscription_files("host", "user", "id", 2222, "/opt/lab-remote-stack")
                )

            upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
