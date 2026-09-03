#!/usr/bin/env python3
"""AutoSSH reverse-tunnel deployment module."""

import shlex
import time

from modules import BaseModule
from utils import print_error, print_info, print_success, print_warning


class AutoSSHModule(BaseModule):
    """Publish the target SSH service through the configured cloud tunnel."""

    def validate(self) -> bool:
        """Validate the server-side identity used by AutoSSH."""
        if not self.config.get("autossh.identity_file"):
            print_error("autossh.identity_file must be configured")
            return False
        return True

    def deploy(self) -> bool:
        """Install, configure, and start the AutoSSH service on the target."""
        print_info("Deploying AutoSSH reverse tunnel...")
        identity_file = self.config.get("autossh.identity_file")
        monitor_port = self.config.get("autossh.monitor_port", 20000)

        if not self._install_autossh():
            return False
        if not self._setup_ssh_key(identity_file):
            return False
        if not self._create_systemd_service(monitor_port, identity_file):
            return False
        if not self._cleanup_reverse_port(identity_file):
            return False
        if not self._start_service():
            return False

        print_success("AutoSSH reverse tunnel deployed successfully")
        return True

    def rollback(self) -> bool:
        """Stop and disable the target's AutoSSH service."""
        print_info("Rolling back AutoSSH deployment...")
        self.context.run("sudo systemctl stop lab-autossh.service 2>/dev/null || true")
        self.context.run("sudo systemctl disable lab-autossh.service 2>/dev/null || true")
        print_success("AutoSSH deployment rolled back")
        return True

    def _install_autossh(self) -> bool:
        print_info("Installing autossh...")
        command = """
if command -v autossh >/dev/null 2>&1; then
    exit 0
elif command -v apt-get >/dev/null 2>&1; then
    if sudo apt-get install -y autossh; then
        exit 0
    fi
    sudo apt-get update -qq && sudo apt-get install -y autossh
elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y autossh
elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y autossh
elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -S --noconfirm autossh
elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y autossh
elif command -v apk >/dev/null 2>&1; then
    sudo apk add autossh
else
    echo "Unknown package manager"
    exit 1
fi
"""
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_error(f"Failed to install autossh: {stderr}")
            return False
        print_success("autossh installed")
        return True

    def _setup_ssh_key(self, identity_file: str) -> bool:
        print_info("Setting up SSH key...")
        tunnel = self.context.cloud_tunnel
        commands = (
            "mkdir -p $HOME/.ssh && chmod 700 $HOME/.ssh",
            f"chmod 600 {shlex.quote(identity_file)}",
            f"ssh-keyscan -H {shlex.quote(tunnel.host)} >> $HOME/.ssh/known_hosts 2>/dev/null || true",
        )
        for command in commands:
            returncode, _, stderr = self.context.run(command)
            if returncode != 0:
                print_error(f"Failed to prepare AutoSSH key: {stderr}")
                return False

        print_info(f"Testing connection to cloud server {tunnel.host}...")
        test_command = (
            f"ssh -i {shlex.quote(identity_file)} -o ConnectTimeout=10 "
            f"-o StrictHostKeyChecking=no {shlex.quote(tunnel.user)}@{shlex.quote(tunnel.host)} "
            "'echo Connection successful'"
        )
        returncode, _, stderr = self.context.run(test_command)
        if returncode != 0:
            print_warning("SSH connection test failed")
            print_info("Make sure:")
            print_info(f"  1. Cloud server {tunnel.host} is accessible")
            print_info(
                f"  2. SSH public key is added to {tunnel.user}@{tunnel.host}:~/.ssh/authorized_keys"
            )
            print_info("  3. SSH service is running on cloud server")
            return False

        print_success("SSH key setup complete")
        return True

    def _cleanup_reverse_port(self, identity_file: str) -> bool:
        print_info("Cleaning stale reverse SSH listener...")
        tunnel = self.context.cloud_tunnel
        cleanup_script = f"""
set +e
if command -v fuser >/dev/null 2>&1; then
    fuser -k -n tcp {tunnel.reverse_port} >/dev/null 2>&1 || true
elif command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -tiTCP:{tunnel.reverse_port} -sTCP:LISTEN 2>/dev/null)
    if [ -n "$pids" ]; then
        kill $pids >/dev/null 2>&1 || true
    fi
fi
exit 0
"""
        command = (
            f"ssh -i {shlex.quote(identity_file)} -o ConnectTimeout=10 "
            f"-o StrictHostKeyChecking=no {shlex.quote(tunnel.user)}@{shlex.quote(tunnel.host)} "
            f"{shlex.quote(cleanup_script)}"
        )
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_warning("Could not clean stale reverse SSH listener")
            if stderr:
                print_info(stderr.strip())
            return False
        print_success("Stale reverse SSH listener cleaned")
        return True

    def _create_systemd_service(self, monitor_port: int, identity_file: str) -> bool:
        print_info("Creating systemd service...")
        tunnel = self.context.cloud_tunnel
        service_content = f"""[Unit]
Description=AutoSSH Reverse Tunnel
After=network.target

[Service]
Type=simple
User={self.context.target.user}
Environment="AUTOSSH_GATETIME=0"
Environment="AUTOSSH_PORT={monitor_port}"
ExecStart=/usr/bin/autossh -M {monitor_port} -N \\
    -o "ServerAliveInterval=30" \\
    -o "ServerAliveCountMax=3" \\
    -o "StrictHostKeyChecking=no" \\
    -o "ExitOnForwardFailure=yes" \\
    -i {identity_file} \\
    -R {tunnel.reverse_bind_address}:{tunnel.reverse_port}:localhost:22 \\
    {tunnel.user}@{tunnel.host}
Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
"""
        command = f"""
sudo tee /etc/systemd/system/lab-autossh.service > /dev/null << 'EOF'
{service_content}
EOF
sudo systemctl daemon-reload
sudo systemctl enable lab-autossh.service
"""
        returncode, _, stderr = self.context.run(command)
        if returncode != 0:
            print_error(f"Failed to create service: {stderr}")
            return False
        print_success("Systemd service created")
        return True

    def _start_service(self) -> bool:
        print_info("Starting AutoSSH service...")
        returncode, _, stderr = self.context.run("sudo systemctl restart lab-autossh.service")
        if returncode != 0:
            print_error(f"Failed to start service: {stderr}")
            return False
        time.sleep(2)
        returncode, stdout, _ = self.context.run("sudo systemctl is-active lab-autossh.service")
        if returncode == 0 and stdout.strip() == "active":
            print_success("AutoSSH service started")
            return True
        print_error("AutoSSH service is not running properly")
        print_info("Check logs with: sudo journalctl -u lab-autossh.service -n 50")
        return False

    def restart_service(self) -> bool:
        """Restart AutoSSH on the resolved deployment target."""
        returncode, _, _ = self.context.run("sudo systemctl restart lab-autossh.service")
        return returncode == 0
