#!/usr/bin/env python3
"""AutoSSH reverse tunnel module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules import BaseModule
from utils import (
    print_error, print_info, print_success, print_warning,
    run_ssh_command, upload_file
)


class AutoSSHModule(BaseModule):
    """AutoSSH reverse tunnel module."""

    def validate(self) -> bool:
        """Validate AutoSSH module prerequisites."""
        # Check if remote server is accessible
        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')

        if not host or not user:
            print_error("Cloud host and user must be configured")
            return False

        # Check if SSH identity file exists
        identity_file = self.config.get('autossh.identity_file')
        if identity_file:
            identity_path = Path(identity_file).expanduser()
            if not identity_path.exists():
                print_error(f"SSH identity file not found: {identity_file}")
                print_info("Generate one with: ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_autossh")
                return False

        return True

    def deploy(self) -> bool:
        """Deploy AutoSSH reverse tunnel."""
        print_info("Deploying AutoSSH reverse tunnel...")

        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')
        identity_file = self.config.get('autossh.identity_file')
        reverse_port = self.config.get('cloud.reverse_port', 2223)
        monitor_port = self.config.get('autossh.monitor_port', 20000)

        # Install autossh
        if not self._install_autossh(host, user, identity_file, reverse_port):
            return False

        # Setup SSH key
        if not self._setup_ssh_key(host, user, identity_file, reverse_port):
            return False

        # Create systemd service
        if not self._create_systemd_service(host, user, identity_file, reverse_port, monitor_port):
            return False

        # Start service
        if not self._start_service(host, user, identity_file, reverse_port):
            return False

        print_success("AutoSSH reverse tunnel deployed successfully")
        return True

    def rollback(self) -> bool:
        """Rollback AutoSSH deployment."""
        print_info("Rolling back AutoSSH deployment...")

        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')
        identity_file = self.config.get('autossh.identity_file')
        reverse_port = self.config.get('cloud.reverse_port', 2223)

        # Stop service
        cmd = "sudo systemctl stop lab-autossh.service 2>/dev/null || true"
        run_ssh_command(host, user, cmd, identity_file, reverse_port)

        # Disable service
        cmd = "sudo systemctl disable lab-autossh.service 2>/dev/null || true"
        run_ssh_command(host, user, cmd, identity_file, reverse_port)

        print_success("AutoSSH deployment rolled back")
        return True

    def _install_autossh(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Install autossh package."""
        print_info("Installing autossh...")

        # Detect package manager and install
        cmd = """
if command -v apt-get >/dev/null 2>&1; then
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
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to install autossh: {stderr}")
            return False

        print_success("autossh installed")
        return True

    def _setup_ssh_key(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Setup SSH key for AutoSSH."""
        print_info("Setting up SSH key...")

        cloud_host = self.config.get('cloud.host')
        cloud_user = self.config.get('cloud.user')

        # Create .ssh directory if not exists
        cmd = f"mkdir -p $HOME/.ssh && chmod 700 $HOME/.ssh"
        run_ssh_command(host, user, cmd, identity_file, port)

        # Upload private key
        local_key = Path(identity_file).expanduser()
        remote_key_path = f"/home/{user}/.ssh/id_autossh"

        if not upload_file(str(local_key), remote_key_path, host, user, identity_file, port):
            print_error("Failed to upload SSH private key")
            return False

        # Set permissions
        cmd = f"chmod 600 $HOME/.ssh/id_autossh"
        run_ssh_command(host, user, cmd, identity_file, port)

        # Add cloud host to known_hosts
        cmd = f"ssh-keyscan -H {cloud_host} >> $HOME/.ssh/known_hosts 2>/dev/null || true"
        run_ssh_command(host, user, cmd, identity_file, port)

        # Test connection to cloud server
        print_info(f"Testing connection to cloud server {cloud_host}...")
        test_cmd = f"ssh -i $HOME/.ssh/id_autossh -o ConnectTimeout=10 -o StrictHostKeyChecking=no {cloud_user}@{cloud_host} 'echo Connection successful'"
        returncode, stdout, stderr = run_ssh_command(host, user, test_cmd, identity_file, port)

        if returncode != 0:
            print_warning("SSH connection test failed")
            print_info("Make sure:")
            print_info(f"  1. Cloud server {cloud_host} is accessible")
            print_info(f"  2. SSH public key is added to {cloud_user}@{cloud_host}:~/.ssh/authorized_keys")
            print_info("  3. SSH service is running on cloud server")
            return False

        print_success("SSH key setup complete")
        return True

    def _create_systemd_service(self, host: str, user: str, identity_file: str, port: int, monitor_port: int) -> bool:
        """Create systemd service for AutoSSH."""
        print_info("Creating systemd service...")

        cloud_host = self.config.get('cloud.host')
        cloud_user = self.config.get('cloud.user')
        reverse_port = self.config.get('cloud.reverse_port', 2223)

        # Get remote SSH port (usually 22)
        remote_ssh_port = 22  # Could make this configurable

        service_content = f"""[Unit]
Description=AutoSSH Reverse Tunnel
After=network.target

[Service]
Type=simple
User={user}
Environment="AUTOSSH_GATETIME=0"
Environment="AUTOSSH_PORT={monitor_port}"
ExecStart=/usr/bin/autossh -M {monitor_port} -N \\
    -o "ServerAliveInterval=30" \\
    -o "ServerAliveCountMax=3" \\
    -o "StrictHostKeyChecking=no" \\
    -o "ExitOnForwardFailure=yes" \\
    -i /home/{user}/.ssh/id_autossh \\
    -R {reverse_port}:localhost:{remote_ssh_port} \\
    {cloud_user}@{cloud_host}
Restart=always
RestartSec=10s

[Install]
WantedBy=multi-user.target
"""

        # Write service file
        cmd = f"""
sudo tee /etc/systemd/system/lab-autossh.service > /dev/null << 'EOF'
{service_content}
EOF
sudo systemctl daemon-reload
sudo systemctl enable lab-autossh.service
"""
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to create service: {stderr}")
            return False

        print_success("Systemd service created")
        return True

    def _start_service(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Start AutoSSH service."""
        print_info("Starting AutoSSH service...")

        cmd = "sudo systemctl start lab-autossh.service"
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to start service: {stderr}")
            return False

        # Wait a bit and check status
        import time
        time.sleep(2)

        cmd = "sudo systemctl is-active lab-autossh.service"
        returncode, stdout, _ = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode == 0 and 'active' in stdout:
            print_success("AutoSSH service started")
            return True
        else:
            print_warning("AutoSSH service may not be running properly")
            print_info("Check logs with: sudo journalctl -u lab-autossh.service -n 50")
            return True  # Continue anyway

    def restart_service(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Restart AutoSSH service."""
        cmd = "sudo systemctl restart lab-autossh.service"
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        return returncode == 0
