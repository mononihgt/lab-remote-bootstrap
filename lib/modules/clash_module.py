#!/usr/bin/env python3
"""Clash proxy deployment module."""

import gzip
import shutil
import tempfile
import time
from pathlib import Path

from modules import BaseModule
from utils import get_project_root, print_error, print_info, print_success, print_warning


class ClashModule(BaseModule):
    """Install and manage Clash on the resolved deployment target."""

    def validate(self) -> bool:
        """Validate local Clash deployment assets."""
        clash_assets = get_project_root() / "assets" / "clash"
        if not clash_assets.exists():
            print_error(f"Clash assets directory is missing: {clash_assets}")
            return False
        return True

    def deploy(self) -> bool:
        """Deploy Clash proxy files and service."""
        print_info("Deploying Clash proxy...")
        install_root = self.config.get("clash.install_root", "/opt/lab-remote-stack")

        for step in (
            lambda: self._create_directories(install_root),
            lambda: self._upload_clash_binary(install_root),
            lambda: self._upload_geo_files(install_root),
            lambda: self._upload_templates(install_root),
            lambda: self._upload_subscription_files(install_root),
            lambda: self._create_systemd_service(install_root),
            self._start_service,
        ):
            if not step():
                return False

        print_success("Clash proxy deployed successfully")
        return True

    def rollback(self) -> bool:
        """Stop and disable the Clash service."""
        print_info("Rolling back Clash deployment...")
        self.context.run("sudo systemctl stop lab-clash.service 2>/dev/null || true")
        self.context.run("sudo systemctl disable lab-clash.service 2>/dev/null || true")
        print_success("Clash deployment rolled back")
        return True

    def _create_directories(self, install_root: str) -> bool:
        self.log("Creating directories")
        command = f"""
sudo mkdir -p {install_root}/clash/templates
sudo chown -R {self.context.target.user}:{self.context.target.user} {install_root}
"""
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_error(f"Failed to create directories: {stderr}")
            return False
        return True

    def _find_binary(self):
        clash_assets = get_project_root() / "assets" / "clash"
        for pattern in ("mihomo*", "CrashCore*", "clash*"):
            for candidate in clash_assets.glob(pattern):
                if candidate.is_file() and candidate.suffix != ".md":
                    return candidate
        return None

    def _upload_clash_binary(self, install_root: str) -> bool:
        print_info("Uploading Clash binary...")
        clash_binary = self._find_binary()
        if not clash_binary:
            print_warning("No Clash binary found, attempting to download...")
            return self._download_clash_binary(install_root)

        upload_source = clash_binary
        temp_dir = None
        try:
            if clash_binary.suffix == ".gz":
                print_info("Extracting gzip archive...")
                temp_dir = tempfile.TemporaryDirectory()
                upload_source = Path(temp_dir.name) / clash_binary.stem
                with gzip.open(clash_binary, "rb") as compressed, open(upload_source, "wb") as extracted:
                    shutil.copyfileobj(compressed, extracted)

            remote_path = f"{install_root}/clash/clash"
            staging_path = f"{remote_path}.upload"
            if not self.context.upload(str(upload_source), staging_path):
                print_error("Failed to upload Clash binary")
                return False
            returncode, _, stderr = self.context.run(
                f"mv -f {staging_path} {remote_path} && chmod +x {remote_path}"
            )
            if returncode != 0:
                print_error(f"Failed to install Clash binary: {stderr}")
                return False
        finally:
            if temp_dir:
                temp_dir.cleanup()

        print_success("Clash binary ready")
        return True

    def _download_clash_binary(self, install_root: str) -> bool:
        self.log("Downloading Clash binary on target")
        returncode, stdout, stderr = self.context.run("uname -m")
        if returncode != 0:
            print_error(f"Failed to detect target architecture: {stderr}")
            return False

        architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(
            stdout.strip(), stdout.strip()
        )
        command = f"""
cd {install_root}/clash
LATEST_URL=$(curl -s https://api.github.com/repos/MetaCubeX/mihomo/releases/latest | grep 'browser_download_url.*linux-{architecture}' | grep -v '.gz' | head -1 | cut -d'"' -f4)
if [ -n "$LATEST_URL" ]; then
    curl -L -o clash "$LATEST_URL"
    chmod +x clash
else
    echo "Failed to get download URL"
    exit 1
fi
"""
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_error(f"Failed to download Clash: {stderr}")
            return False
        print_success("Clash binary ready")
        return True

    def _upload_geo_files(self, install_root: str) -> bool:
        print_info("Uploading geo data files...")
        clash_assets = get_project_root() / "assets" / "clash"
        for filename in ("geoip.dat", "geosite.dat"):
            local_file = clash_assets / filename
            if not local_file.exists():
                continue
            target_path = f"{install_root}/clash/{filename}"
            if self.context.upload(str(local_file), target_path):
                continue
            print_warning(f"Failed to upload {filename}, downloading it on target")
            self.context.run(
                f"cd {install_root}/clash && curl -L -o {filename} "
                f"https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/{filename} || true"
            )
        return True

    def _upload_templates(self, install_root: str) -> bool:
        print_info("Uploading templates...")
        templates_dir = get_project_root() / "assets" / "clash" / "templates"
        for template_file in templates_dir.glob("*.yaml"):
            if not self.context.upload(
                str(template_file), f"{install_root}/clash/templates/{template_file.name}"
            ):
                print_warning(f"Failed to upload {template_file.name}")
        return True

    def _upload_subscription_files(self, install_root: str) -> bool:
        config_dir = get_project_root() / "config"
        files = (
            (config_dir / "subscriptions.json", f"{install_root}/clash/subscriptions.json"),
            (config_dir / "clash.generated.yaml", f"{install_root}/clash/config.yaml"),
        )
        for local_file, target_path in files:
            if local_file.exists() and not self.context.upload(str(local_file), target_path):
                print_warning(f"Failed to upload {local_file.name}")
        return True

    def _create_systemd_service(self, install_root: str) -> bool:
        print_info("Creating systemd service...")
        service_content = f"""[Unit]
Description=Clash Proxy Service
After=network.target

[Service]
Type=simple
User={self.context.target.user}
WorkingDirectory={install_root}/clash
ExecStart={install_root}/clash/clash -d {install_root}/clash
Restart=on-failure
RestartSec=5s
Environment="CLASH_HTTP_PORT={self.config.get('clash.http_port', 7890)}"
Environment="CLASH_SOCKS_PORT={self.config.get('clash.socks_port', 7891)}"
Environment="CLASH_API_PORT={self.config.get('clash.api_port', 9090)}"

[Install]
WantedBy=multi-user.target
"""
        command = f"""
sudo tee /etc/systemd/system/lab-clash.service > /dev/null << 'EOF'
{service_content}
EOF
sudo systemctl daemon-reload
sudo systemctl enable lab-clash.service
"""
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_error(f"Failed to create service: {stderr}")
            return False
        print_success("Systemd service created")
        return True

    def _start_service(self) -> bool:
        print_info("Starting Clash service...")
        returncode, _, stderr = self.context.run("sudo systemctl restart lab-clash.service")
        if returncode != 0:
            print_error(f"Failed to start service: {stderr}")
            return False
        time.sleep(2)
        returncode, stdout, _ = self.context.run("sudo systemctl is-active lab-clash.service")
        if returncode == 0 and "active" in stdout:
            print_success("Clash service started")
        else:
            print_warning("Clash service may not be running properly")
            print_info("Check logs with: sudo journalctl -u lab-clash.service -n 50")
        return True

    def restart_service(self) -> bool:
        """Restart Clash on the resolved deployment target."""
        returncode, _, _ = self.context.run("sudo systemctl restart lab-clash.service")
        return returncode == 0
