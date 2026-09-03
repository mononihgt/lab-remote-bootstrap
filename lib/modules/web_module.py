#!/usr/bin/env python3
"""Web interface deployment module."""

import time

from modules import BaseModule
from utils import get_project_root, print_error, print_info, print_success, print_warning


class WebModule(BaseModule):
    """Install and manage the Web interface on the deployment target."""

    def validate(self) -> bool:
        """Validate files required for the Web deployment."""
        if not self.config.get("web.enabled", True):
            print_info("Web interface is disabled in config")
            return True
        requirements = get_project_root() / "requirements.txt"
        if not requirements.exists():
            print_error(f"Requirements file missing: {requirements}")
            return False
        return True

    def deploy(self) -> bool:
        """Deploy the Web application and its systemd service."""
        if not self.config.get("web.enabled", True):
            print_info("Web interface disabled, skipping")
            return True

        print_info("Deploying Web interface...")
        install_root = self.config.get("clash.install_root", "/opt/lab-remote-stack")
        for step in (
            lambda: self._create_directories(install_root),
            lambda: self._upload_web_app(install_root),
            lambda: self._install_dependencies(install_root),
            lambda: self._create_systemd_service(install_root),
            self._start_service,
        ):
            if not step():
                return False

        print_success("Web interface deployed successfully")
        return True

    def rollback(self) -> bool:
        """Stop and disable the Web service."""
        print_info("Rolling back Web deployment...")
        self.context.run("sudo systemctl stop lab-web.service 2>/dev/null || true")
        self.context.run("sudo systemctl disable lab-web.service 2>/dev/null || true")
        print_success("Web deployment rolled back")
        return True

    def _create_directories(self, install_root: str) -> bool:
        self.log("Creating web directories")
        command = f"""
sudo mkdir -p {install_root}/web/templates
sudo mkdir -p {install_root}/web/static/css
sudo mkdir -p {install_root}/web/static/js
sudo mkdir -p {install_root}/lib
sudo chown -R {self.context.target.user}:{self.context.target.user} {install_root}/web
sudo chown -R {self.context.target.user}:{self.context.target.user} {install_root}/lib
"""
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_error(f"Failed to create directories: {stderr}")
            return False
        return True

    def _upload_required(self, source, destination: str, description: str) -> bool:
        if self.context.upload(str(source), destination):
            return True
        print_error(f"Failed to upload {description}")
        return False

    def _upload_web_app(self, install_root: str) -> bool:
        print_info("Uploading web application...")
        project_root = get_project_root()
        web_dir = project_root / "web"

        required_files = (
            (web_dir / "app.py", f"{install_root}/web/app.py", "app.py"),
            (project_root / "requirements.txt", f"{install_root}/web/requirements.txt", "requirements.txt"),
        )
        for source, destination, description in required_files:
            if not source.exists():
                print_error(f"Required Web file missing: {source}")
                return False
            if not self._upload_required(source, destination, description):
                return False

        for module_name in (
            "config.py",
            "deployment.py",
            "subscription.py",
            "subscription_paths.py",
            "health.py",
            "utils.py",
        ):
            source = project_root / "lib" / module_name
            if not source.exists():
                print_error(f"Required runtime module missing: {source}")
                return False
            if not self._upload_required(source, f"{install_root}/lib/{module_name}", module_name):
                return False

        directories = (
            (web_dir / "templates", "*.html", f"{install_root}/web/templates"),
            (web_dir / "static" / "css", "*.css", f"{install_root}/web/static/css"),
            (web_dir / "static" / "js", "*.js", f"{install_root}/web/static/js"),
        )
        for source_dir, pattern, destination_dir in directories:
            if not source_dir.exists():
                continue
            for source in source_dir.glob(pattern):
                if not self.context.upload(str(source), f"{destination_dir}/{source.name}"):
                    print_warning(f"Failed to upload {source.name}")

        print_success("Web application uploaded")
        return True

    def _install_dependencies(self, install_root: str) -> bool:
        print_info("Installing Python dependencies...")
        venv_path = f"{install_root}/web/.venv"
        venv_python = f"{venv_path}/bin/python"
        command = f"""
set -e
if command -v uv >/dev/null 2>&1; then
    uv venv --allow-existing --python 3.12 {venv_path}
    uv pip install --python {venv_python} -r {install_root}/web/requirements.txt
elif command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv {venv_path}
    {venv_python} -m pip install --quiet -r {install_root}/web/requirements.txt
else
    echo "Python 3.12 is required for the Web service. Install uv or python3.12." >&2
    exit 1
fi
"""
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_error(f"Failed to install Web dependencies: {stderr}")
            return False
        print_success("Dependencies installed")
        return True

    def _create_systemd_service(self, install_root: str) -> bool:
        print_info("Creating systemd service...")
        venv_python = f"{install_root}/web/.venv/bin/python"
        service_content = f"""[Unit]
Description=Lab Remote Bootstrap Web Interface
After=network.target lab-clash.service

[Service]
Type=simple
User={self.context.target.user}
WorkingDirectory={install_root}/web
Environment="PYTHONPATH={install_root}"
ExecStart={venv_python} {install_root}/web/app.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""
        command = f"""
sudo tee /etc/systemd/system/lab-web.service > /dev/null << 'EOF'
{service_content}
EOF
sudo systemctl daemon-reload
sudo systemctl enable lab-web.service
"""
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_error(f"Failed to create service: {stderr}")
            return False
        print_success("Systemd service created")
        return True

    def _start_service(self) -> bool:
        print_info("Starting Web service...")
        returncode, _, stderr = self.context.run("sudo systemctl start lab-web.service")
        if returncode != 0:
            print_error(f"Failed to start Web service: {stderr}")
            return False
        time.sleep(2)
        returncode, stdout, _ = self.context.run("sudo systemctl is-active lab-web.service")
        if returncode == 0 and stdout.strip() == "active":
            print_success("Web service started")
            return True
        print_error("Web service is not running properly")
        print_info("Check logs with: sudo journalctl -u lab-web.service -n 50")
        return False

    def restart_service(self) -> bool:
        """Restart Web on the resolved deployment target."""
        returncode, _, _ = self.context.run("sudo systemctl restart lab-web.service")
        return returncode == 0
