#!/usr/bin/env python3
"""Clash proxy module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules import BaseModule
from utils import (
    print_error, print_info, print_success, print_warning,
    run_ssh_command, upload_file, get_project_root
)


class ClashModule(BaseModule):
    """Clash proxy deployment module."""

    def validate(self) -> bool:
        """Validate Clash module prerequisites."""
        # Check if remote server is accessible
        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')

        if not host or not user:
            print_error("Cloud host and user must be configured")
            return False

        # Check if Clash binary exists
        project_root = get_project_root()
        clash_assets = project_root / "assets" / "clash"

        # Look for Clash binary
        clash_binary = None
        for pattern in ['mihomo*', 'clash*', 'CrashCore*']:
            matches = list(clash_assets.glob(pattern))
            if matches:
                clash_binary = matches[0]
                break

        if not clash_binary:
            print_warning("No Clash binary found in assets/clash/")
            print_info("You can:")
            print_info("  1. Download mihomo from https://github.com/MetaCubeX/mihomo/releases")
            print_info("  2. Place it in assets/clash/")
            print_info("  3. Or the script will try to download it automatically")

        return True

    def deploy(self) -> bool:
        """Deploy Clash proxy."""
        print_info("Deploying Clash proxy...")

        host, user, identity_file, reverse_port, _ = self.get_deployment_params()
        install_root = self.config.get('clash.install_root', '/opt/lab-remote-stack')

        # Create directories
        if not self._create_directories(host, user, identity_file, reverse_port, install_root):
            return False

        # Upload Clash binary
        if not self._upload_clash_binary(host, user, identity_file, reverse_port, install_root):
            return False

        # Upload geo data files
        if not self._upload_geo_files(host, user, identity_file, reverse_port, install_root):
            return False

        # Upload templates
        if not self._upload_templates(host, user, identity_file, reverse_port, install_root):
            return False

        # Upload local subscription state/config if present
        if not self._upload_subscription_files(host, user, identity_file, reverse_port, install_root):
            return False

        # Create systemd service
        if not self._create_systemd_service(host, user, identity_file, reverse_port, install_root):
            return False

        # Start service
        if not self._start_service(host, user, identity_file, reverse_port):
            return False

        print_success("Clash proxy deployed successfully")
        return True

    def rollback(self) -> bool:
        """Rollback Clash deployment."""
        print_info("Rolling back Clash deployment...")

        host, user, identity_file, reverse_port, _ = self.get_deployment_params()

        # Stop service
        cmd = "sudo systemctl stop lab-clash.service 2>/dev/null || true"
        run_ssh_command(host, user, cmd, identity_file, reverse_port)

        # Disable service
        cmd = "sudo systemctl disable lab-clash.service 2>/dev/null || true"
        run_ssh_command(host, user, cmd, identity_file, reverse_port)

        print_success("Clash deployment rolled back")
        return True

    def _create_directories(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Create necessary directories."""
        self.log("Creating directories")

        cmd = f"""
sudo mkdir -p {install_root}/clash
sudo mkdir -p {install_root}/clash/templates
sudo chown -R {user}:{user} {install_root}
"""
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to create directories: {stderr}")
            return False

        return True

    def _upload_clash_binary(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Upload Clash binary."""
        print_info("Uploading Clash binary...")

        project_root = get_project_root()
        clash_assets = project_root / "assets" / "clash"

        # Find Clash binary
        clash_binary = None
        for pattern in ['mihomo*', 'CrashCore*', 'clash*']:
            matches = list(clash_assets.glob(pattern))
            if matches:
                # Filter out .md files
                matches = [m for m in matches if not m.suffix == '.md']
                if matches:
                    clash_binary = matches[0]
                    break

        if not clash_binary:
            print_warning("No Clash binary found, attempting to download...")
            if not self._download_clash_binary(host, user, identity_file, port, install_root):
                return False
        else:
            self.log(f"Found binary: {clash_binary.name}")

            # Handle .gz files
            if clash_binary.suffix == '.gz':
                print_info("Extracting gzip archive...")
                import gzip
                import shutil
                extracted = clash_binary.parent / clash_binary.stem
                with gzip.open(clash_binary, 'rb') as f_in:
                    with open(extracted, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                clash_binary = extracted

            # Upload
            remote_path = f"{install_root}/clash/clash"
            if not upload_file(str(clash_binary), remote_path, host, user, identity_file, port):
                print_error("Failed to upload Clash binary")
                return False

            # Make executable
            cmd = f"chmod +x {install_root}/clash/clash"
            run_ssh_command(host, user, cmd, identity_file, port)

        print_success("Clash binary ready")
        return True

    def _download_clash_binary(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Download Clash binary on remote server."""
        self.log("Downloading Clash binary on remote server")

        # Detect architecture
        cmd = "uname -m"
        returncode, stdout, _ = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            return False

        arch = stdout.strip()
        if arch == 'x86_64':
            arch = 'amd64'
        elif arch == 'aarch64':
            arch = 'arm64'

        # Download latest mihomo
        download_cmd = f"""
cd {install_root}/clash
LATEST_URL=$(curl -s https://api.github.com/repos/MetaCubeX/mihomo/releases/latest | grep 'browser_download_url.*linux-{arch}' | grep -v '.gz' | head -1 | cut -d'"' -f4)
if [ -n "$LATEST_URL" ]; then
    curl -L -o clash "$LATEST_URL"
    chmod +x clash
    echo "Downloaded successfully"
else
    echo "Failed to get download URL"
    exit 1
fi
"""
        returncode, stdout, stderr = run_ssh_command(host, user, download_cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to download Clash: {stderr}")
            return False

        print_success("Downloaded Clash binary")
        return True

    def _upload_geo_files(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Upload geo data files."""
        print_info("Uploading geo data files...")

        project_root = get_project_root()
        clash_assets = project_root / "assets" / "clash"

        for filename in ['geoip.dat', 'geosite.dat']:
            local_file = clash_assets / filename
            if local_file.exists():
                remote_path = f"{install_root}/clash/{filename}"
                if upload_file(str(local_file), remote_path, host, user, identity_file, port):
                    self.log(f"Uploaded {filename}")
                else:
                    print_warning(f"Failed to upload {filename}, will download on server")
                    # Download on server
                    cmd = f"""
cd {install_root}/clash
curl -L -o {filename} https://github.com/Loyalsoldier/v2ray-rules-dat/releases/latest/download/{filename} || true
"""
                    run_ssh_command(host, user, cmd, identity_file, port)

        return True

    def _upload_templates(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Upload subscription templates."""
        print_info("Uploading templates...")

        project_root = get_project_root()
        templates_dir = project_root / "assets" / "clash" / "templates"

        for template_file in templates_dir.glob('*.yaml'):
            remote_path = f"{install_root}/clash/templates/{template_file.name}"
            if not upload_file(str(template_file), remote_path, host, user, identity_file, port):
                print_warning(f"Failed to upload {template_file.name}")

        return True

    def _upload_subscription_files(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Upload local subscription state and generated Clash config if present."""
        project_root = get_project_root()
        config_dir = project_root / "config"
        files = [
            (config_dir / "subscriptions.json", f"{install_root}/clash/subscriptions.json"),
            (config_dir / "clash.generated.yaml", f"{install_root}/clash/config.yaml"),
        ]

        for local_file, remote_path in files:
            if not local_file.exists():
                continue
            if not upload_file(str(local_file), remote_path, host, user, identity_file, port):
                print_warning(f"Failed to upload {local_file.name}")

        return True

    def _create_systemd_service(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Create systemd service for Clash."""
        print_info("Creating systemd service...")

        clash_http_port = self.config.get('clash.http_port', 7890)
        clash_socks_port = self.config.get('clash.socks_port', 7891)
        clash_api_port = self.config.get('clash.api_port', 9090)

        service_content = f"""[Unit]
Description=Clash Proxy Service
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={install_root}/clash
ExecStart={install_root}/clash/clash -d {install_root}/clash
Restart=on-failure
RestartSec=5s

Environment="CLASH_HTTP_PORT={clash_http_port}"
Environment="CLASH_SOCKS_PORT={clash_socks_port}"
Environment="CLASH_API_PORT={clash_api_port}"

[Install]
WantedBy=multi-user.target
"""

        # Write service file
        cmd = f"""
sudo tee /etc/systemd/system/lab-clash.service > /dev/null << 'EOF'
{service_content}
EOF
sudo systemctl daemon-reload
sudo systemctl enable lab-clash.service
"""
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to create service: {stderr}")
            return False

        print_success("Systemd service created")
        return True

    def _start_service(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Start Clash service."""
        print_info("Starting Clash service...")

        cmd = "sudo systemctl start lab-clash.service"
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to start service: {stderr}")
            return False

        # Wait a bit and check status
        import time
        time.sleep(2)

        cmd = "sudo systemctl is-active lab-clash.service"
        returncode, stdout, _ = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode == 0 and 'active' in stdout:
            print_success("Clash service started")
            return True
        else:
            print_warning("Clash service may not be running properly")
            print_info("Check logs with: sudo journalctl -u lab-clash.service -n 50")
            return True  # Continue anyway

    def restart_service(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Restart Clash service."""
        cmd = "sudo systemctl restart lab-clash.service"
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        return returncode == 0
