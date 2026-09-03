#!/usr/bin/env python3
"""AutoSSH reverse tunnel module."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from modules import BaseModule
from utils import (
    print_error, print_info, print_success, print_warning,
    run_ssh_command
)


class AutoSSHModule(BaseModule):
    """AutoSSH reverse tunnel module."""

    def validate(self) -> bool:
        """Validate AutoSSH module prerequisites."""
        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')

        if not host or not user:
            print_error("Cloud host and user must be configured")
            return False

        control_identity_file = self.config.get('deployment.ssh_identity_file')
        if control_identity_file:
            control_identity_path = Path(control_identity_file).expanduser()
            if not control_identity_path.exists():
                print_error(f"Deployment SSH identity file not found: {control_identity_file}")
                print_info("Set deployment.ssh_identity_file to a local key, or omit it to use SSH config/agent")
                return False

        autossh_identity_file = self.config.get('autossh.identity_file')
        if not autossh_identity_file:
            print_error("AutoSSH identity file must be configured")
            return False

        return True

    def deploy(self) -> bool:
        """Deploy AutoSSH reverse tunnel."""
        print_info("Deploying AutoSSH reverse tunnel...")

        host, user, control_identity_file, reverse_port, _ = self.get_deployment_params()
        autossh_identity_file = self.config.get('autossh.identity_file')
        monitor_port = self.config.get('autossh.monitor_port', 20000)

        # Install autossh
        if not self._install_autossh(host, user, control_identity_file, reverse_port):
            return False

        # Setup SSH key
        if not self._setup_ssh_key(
            host,
            user,
            control_identity_file,
            reverse_port,
            autossh_identity_file,
        ):
            return False

        # Create systemd service
        if not self._create_systemd_service(
            host,
            user,
            control_identity_file,
            reverse_port,
            monitor_port,
            autossh_identity_file,
        ):
            return False

        # Clean any stale cloud-side listener before restarting the tunnel.
        if not self._cleanup_reverse_port(
            host,
            user,
            control_identity_file,
            reverse_port,
            autossh_identity_file,
        ):
            return False

        # Start service
        if not self._start_service(host, user, control_identity_file, reverse_port):
            return False

        print_success("AutoSSH reverse tunnel deployed successfully")
        return True

    def rollback(self) -> bool:
        """Rollback AutoSSH deployment."""
        print_info("Rolling back AutoSSH deployment...")

        host, user, control_identity_file, reverse_port, _ = self.get_deployment_params()

        # Stop service
        cmd = "sudo systemctl stop lab-autossh.service 2>/dev/null || true"
        run_ssh_command(host, user, cmd, control_identity_file, reverse_port)

        # Disable service
        cmd = "sudo systemctl disable lab-autossh.service 2>/dev/null || true"
        run_ssh_command(host, user, cmd, control_identity_file, reverse_port)

        print_success("AutoSSH deployment rolled back")
        return True

    def _install_autossh(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Install autossh package."""
        print_info("Installing autossh...")

        # Detect package manager and install
        cmd = """
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
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to install autossh: {stderr}")
            return False

        print_success("autossh installed")
        return True

    def _setup_ssh_key(
        self,
        host: str,
        user: str,
        control_identity_file: str,
        port: int,
        autossh_identity_file: str,
    ) -> bool:
        """Setup SSH key for AutoSSH."""
        print_info("Setting up SSH key...")

        cloud_host = self.config.get('cloud.host')
        cloud_user = self.config.get('cloud.user')

        # Create .ssh directory if not exists
        cmd = f"mkdir -p $HOME/.ssh && chmod 700 $HOME/.ssh"
        run_ssh_command(host, user, cmd, control_identity_file, port)

        # Set permissions
        cmd = f"chmod 600 {autossh_identity_file}"
        run_ssh_command(host, user, cmd, control_identity_file, port)

        # Add cloud host to known_hosts
        cmd = f"ssh-keyscan -H {cloud_host} >> $HOME/.ssh/known_hosts 2>/dev/null || true"
        run_ssh_command(host, user, cmd, control_identity_file, port)

        # Test connection to cloud server
        print_info(f"Testing connection to cloud server {cloud_host}...")
        test_cmd = f"ssh -i {autossh_identity_file} -o ConnectTimeout=10 -o StrictHostKeyChecking=no {cloud_user}@{cloud_host} 'echo Connection successful'"
        returncode, stdout, stderr = run_ssh_command(host, user, test_cmd, control_identity_file, port)

        if returncode != 0:
            print_warning("SSH connection test failed")
            print_info("Make sure:")
            print_info(f"  1. Cloud server {cloud_host} is accessible")
            print_info(f"  2. SSH public key is added to {cloud_user}@{cloud_host}:~/.ssh/authorized_keys")
            print_info("  3. SSH service is running on cloud server")
            return False

        print_success("SSH key setup complete")
        return True

    def _cleanup_reverse_port(
        self,
        host: str,
        user: str,
        control_identity_file: str,
        port: int,
        autossh_identity_file: str,
    ) -> bool:
        """Clear stale cloud-side listeners for the reverse SSH port."""
        print_info("Cleaning stale reverse SSH listener...")

        cloud_host = self.config.get('cloud.host')
        cloud_user = self.config.get('cloud.user')
        reverse_port = self.config.get('cloud.reverse_port', 2223)

        cleanup_script = f"""
set +e
if command -v fuser >/dev/null 2>&1; then
    fuser -k -n tcp {reverse_port} >/dev/null 2>&1 || true
elif command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -tiTCP:{reverse_port} -sTCP:LISTEN 2>/dev/null)
    if [ -n "$pids" ]; then
        kill $pids >/dev/null 2>&1 || true
    fi
fi
exit 0
"""
        cmd = (
            f"ssh -i {autossh_identity_file} "
            f"-o ConnectTimeout=10 "
            f"-o StrictHostKeyChecking=no "
            f"{cloud_user}@{cloud_host} "
            f"'{cleanup_script}'"
        )

        returncode, _, stderr = run_ssh_command(host, user, cmd, control_identity_file, port)
        if returncode != 0:
            print_warning("Could not clean stale reverse SSH listener")
            if stderr:
                print_info(stderr.strip())
            return False

        print_success("Stale reverse SSH listener cleaned")
        return True

    def _create_systemd_service(
        self,
        host: str,
        user: str,
        control_identity_file: str,
        port: int,
        monitor_port: int,
        autossh_identity_file: str,
    ) -> bool:
        """Create systemd service for AutoSSH."""
        print_info("Creating systemd service...")

        cloud_host = self.config.get('cloud.host')
        cloud_user = self.config.get('cloud.user')
        reverse_port = self.config.get('cloud.reverse_port', 2223)
        reverse_bind_address = self.config.get('cloud.reverse_bind_address', '0.0.0.0')

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
    -i {autossh_identity_file} \\
    -R {reverse_bind_address}:{reverse_port}:localhost:{remote_ssh_port} \\
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
        returncode, _, stderr = run_ssh_command(host, user, cmd, control_identity_file, port)
        if returncode != 0:
            print_error(f"Failed to create service: {stderr}")
            return False

        print_success("Systemd service created")
        return True

    def _start_service(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Start AutoSSH service."""
        print_info("Starting AutoSSH service...")

        cmd = "sudo systemctl restart lab-autossh.service"
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode != 0:
            print_error(f"Failed to start service: {stderr}")
            return False

        # Wait a bit and check status
        import time
        time.sleep(2)

        cmd = "sudo systemctl is-active lab-autossh.service"
        returncode, stdout, _ = run_ssh_command(host, user, cmd, identity_file, port)
        if returncode == 0 and stdout.strip() == 'active':
            print_success("AutoSSH service started")
            return True
        else:
            print_error("AutoSSH service is not running properly")
            print_info("Check logs with: sudo journalctl -u lab-autossh.service -n 50")
            return False

    def restart_service(self, host: str, user: str, identity_file: str, port: int) -> bool:
        """Restart AutoSSH service."""
        cmd = "sudo systemctl restart lab-autossh.service"
        returncode, _, stderr = run_ssh_command(host, user, cmd, identity_file, port)
        return returncode == 0
