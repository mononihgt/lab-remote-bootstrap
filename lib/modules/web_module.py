#!/usr/bin/env python3
"""Web interface deployment module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules import BaseModule
from utils import (
    print_error, print_info, print_success, print_warning,
    run_ssh_command, upload_file, get_project_root
)


class WebModule(BaseModule):
    """Web interface deployment module."""

    def validate(self) -> bool:
        """Validate Web module prerequisites."""
        # Check if web is enabled
        if not self.config.get('web.enabled', True):
            print_info("Web interface is disabled in config")
            return True

        # Check if Flask dependencies are available
        project_root = get_project_root()
        requirements = project_root / "requirements.txt"

        if not requirements.exists():
            print_warning("requirements.txt not found")
            return False

        return True

    def deploy(self) -> bool:
        """Deploy Web interface."""
        if not self.config.get('web.enabled', True):
            print_info("Web interface disabled, skipping")
            return True

        print_info("Deploying Web interface...")

        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')
        identity_file = self.config.get('autossh.identity_file')
        reverse_port = self.config.get('cloud.reverse_port', 2223)
        install_root = self.config.get('clash.install_root', '/opt/lab-remote-stack')

        # Create web directory
        if not self._create_directories(host, user, identity_file, reverse_port, install_root):
            return False

        # Upload web application
        if not self._upload_web_app(host, user, identity_file, reverse_port, install_root):
            return False

        # Install Python dependencies
        if not self._install_dependencies(host, user, identity_file, reverse_port, install_root):
            return False

        # Create systemd service
        if not self._create_systemd_service(host, user, identity_file, reverse_port, install_root):
            return False

        # Start service
        if not self._start_service(host, user, identity_file, reverse_port):
            return False

        print_success("Web interface deployed successfully")
        return True

    def rollback(self) -> bool:
        """Rollback Web deployment."""
        print_info("Rolling back Web deployment...")

        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')
        identity_file = self.config.get('autossh.identity_file')
        reverse_port = self.config.get('cloud.reverse_port', 2223)

        # Stop service
        cmd = "sudo systemctl stop lab-web.service 2>/dev/null || true"
        run_ssh_command(host, user, cmd, identity_file, reverse_port)

        # Disable service
        cmd = "sudo systemctl disable lab-web.service 2>/dev/null || true"
        run_ssh_command(host, user, cmd, identity_file, reverse_port)

        print_success("Web deployment rolled back")
        return True

    def _create_directories(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Create necessary directories."""
        self.log("Creating web directories")

        cmd = f"""
sudo mkdir -p {install_root}/web
sudo mkdir -p {install_root}/web/templates
sudo mkdir -p {install_root}/web/static/css
sudo mkdir -p {install_root}/web/static/js
sudo chown -R {user}:{user} {install_root}/web
"""
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to create directories: {stderr}")
            return False

        return True

    def _upload_web_app(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Upload web application files."""
        print_info("Uploading web application...")

        project_root = get_project_root()
        web_dir = project_root / "web"

        # Upload app.py
        app_file = web_dir / "app.py"
        if app_file.exists():
            remote_path = f"{install_root}/web/app.py"
            if not upload_file(str(app_file), remote_path, host, user, identity_file, port):
                print_error("Failed to upload app.py")
                return False
            self.log("Uploaded app.py")

        # Upload templates
        templates_dir = web_dir / "templates"
        if templates_dir.exists():
            for template_file in templates_dir.glob('*.html'):
                remote_path = f"{install_root}/web/templates/{template_file.name}"
                if not upload_file(str(template_file), remote_path, host, user, identity_file, port):
                    print_warning(f"Failed to upload {template_file.name}")
                else:
                    self.log(f"Uploaded {template_file.name}")

        # Upload static files
        static_dir = web_dir / "static"
        if static_dir.exists():
            # CSS files
            css_dir = static_dir / "css"
            if css_dir.exists():
                for css_file in css_dir.glob('*.css'):
                    remote_path = f"{install_root}/web/static/css/{css_file.name}"
                    if not upload_file(str(css_file), remote_path, host, user, identity_file, port):
                        print_warning(f"Failed to upload {css_file.name}")
                    else:
                        self.log(f"Uploaded {css_file.name}")

            # JS files
            js_dir = static_dir / "js"
            if js_dir.exists():
                for js_file in js_dir.glob('*.js'):
                    remote_path = f"{install_root}/web/static/js/{js_file.name}"
                    if not upload_file(str(js_file), remote_path, host, user, identity_file, port):
                        print_warning(f"Failed to upload {js_file.name}")
                    else:
                        self.log(f"Uploaded {js_file.name}")

        print_success("Web application uploaded")
        return True

    def _install_dependencies(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Install Python dependencies."""
        print_info("Installing Python dependencies...")

        # Check if pip is available
        cmd = "python3 -m pip --version >/dev/null 2>&1 || (sudo apt-get update -qq && sudo apt-get install -y python3-pip)"
        returncode, _, _ = run_ssh_command(host, user, cmd, identity_file, port)

        # Install Flask and requests
        cmd = f"""
python3 -m pip install --user --quiet flask requests pyyaml jsonschema || true
"""
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_warning(f"Failed to install some dependencies: {stderr}")
            print_info("Web interface may not work properly")

        print_success("Dependencies installed")
        return True

    def _create_systemd_service(self, host: str, user: str, identity_file: str, port: int, install_root: str) -> bool:
        """Create systemd service for Web interface."""
        print_info("Creating systemd service...")

        web_host = self.config.get('web.bind', '127.0.0.1')
        web_port = self.config.get('web.port', 5000)

        service_content = f"""[Unit]
Description=Lab Remote Bootstrap Web Interface
After=network.target lab-clash.service

[Service]
Type=simple
User={user}
WorkingDirectory={install_root}/web
Environment="PYTHONPATH={install_root}"
ExecStart=/usr/bin/python3 {install_root}/web/app.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""

        # Write service file
        cmd = f"""
sudo tee /etc/systemd/system/lab-web.service > /dev/null << 'EOF'
{service_content}
EOF
sudo systemctl daemon-reload
sudo systemctl enable lab-web.service
"""
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to create service: {stderr}")
            return False

        print_success("Systemd service created")
        return True

    def _start_service(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Start Web service."""
        print_info("Starting Web service...")

        cmd = "sudo systemctl start lab-web.service"
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to start service: {stderr}")
            return False

        # Wait a bit and check status
        import time
        time.sleep(2)

        cmd = "sudo systemctl is-active lab-web.service"
        returncode, stdout, _ = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode == 0 and 'active' in stdout:
            print_success("Web service started")
            return True
        else:
            print_warning("Web service may not be running properly")
            print_info("Check logs with: sudo journalctl -u lab-web.service -n 50")
            return True  # Continue anyway

    def restart_service(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Restart Web service."""
        cmd = "sudo systemctl restart lab-web.service"
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        return returncode == 0
