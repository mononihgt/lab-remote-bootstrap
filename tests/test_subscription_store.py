import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
    is_remote_deployment = True

    def get(self, key_path, default=None):
        values = {
            "target.host": "lab.example.com",
            "target.user": "labuser",
            "target.ssh_port": 2222,
            "target.ssh_identity_file": "~/.ssh/id_target",
            "cloud.host": "203.0.113.10",
            "cloud.user": "clouduser",
            "cloud.reverse_port": 2223,
            "clash.install_root": "/opt/lab-remote-stack",
        }
        return values.get(key_path, default)


class SpaceInstallRootConfig(FakeConfig):
    def get(self, key_path, default=None):
        if key_path == "clash.install_root":
            return "/opt/lab stack"
        return super().get(key_path, default)


class SubscriptionStoreTests(unittest.TestCase):
    def test_remote_live_store_downloads_and_uploads_live_files(self):
        from subscription_store import SubscriptionStore

        remote_state = {
            "version": "1.0",
            "active": None,
            "subscriptions": [],
        }

        def fake_download(remote_path, local_path, host, user, identity_file, port):
            self.assertEqual(remote_path, "/opt/lab-remote-stack/clash/subscriptions.json")
            self.assertEqual(host, "lab.example.com")
            self.assertEqual(user, "labuser")
            self.assertEqual(identity_file, "~/.ssh/id_target")
            self.assertEqual(port, 2222)
            Path(local_path).write_text(json.dumps(remote_state))
            return True

        uploads = []

        def fake_upload(local_path, remote_path, host, user, identity_file, port):
            uploads.append((Path(local_path).name, remote_path, host, user, identity_file, port))
            return True

        with patch("subscription_store.run_ssh_command", return_value=(0, "", "")), \
             patch("subscription_store.download_file", side_effect=fake_download), \
             patch("subscription_store.upload_file", side_effect=fake_upload):
            store = SubscriptionStore(FakeConfig(), scope="live")
            store.prepare()
            store.local_paths.config_file.write_text("mixed-port: 7890\n")
            store.sync(upload_config=True)
            store.cleanup()

        self.assertEqual(
            uploads,
            [
                (
                    "subscriptions.json",
                    "/opt/lab-remote-stack/clash/subscriptions.json",
                    "lab.example.com",
                    "labuser",
                    "~/.ssh/id_target",
                    2222,
                ),
                (
                    "config.yaml",
                    "/opt/lab-remote-stack/clash/config.yaml",
                    "lab.example.com",
                    "labuser",
                    "~/.ssh/id_target",
                    2222,
                ),
            ],
        )

    def test_remote_live_store_quotes_paths_in_ssh_commands(self):
        from subscription_store import SubscriptionStore

        commands = []

        def fake_ssh(_host, _user, command, _identity_file, _port):
            commands.append(command)
            return 1 if command.startswith("test -f ") else 0, "", ""

        with patch("subscription_store.run_ssh_command", side_effect=fake_ssh), \
             patch("subscription_store.upload_file", return_value=True):
            store = SubscriptionStore(SpaceInstallRootConfig(), scope="live")
            store.prepare()
            store.local_paths.subscriptions_file.write_text(json.dumps({"subscriptions": []}))
            store.sync(upload_config=False)
            store.cleanup()

        self.assertEqual(
            commands,
            [
                "test -f '/opt/lab stack/clash/subscriptions.json'",
                "mkdir -p '/opt/lab stack/clash'",
            ],
        )


if __name__ == "__main__":
    unittest.main()
