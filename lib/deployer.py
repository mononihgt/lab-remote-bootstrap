#!/usr/bin/env python3
"""Main deployment coordinator."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from modules.clash_module import ClashModule
from modules.autossh_module import AutoSSHModule
from modules.zsh_module import ZshModule
from modules.web_module import WebModule
from utils import (
    print_error, print_info, print_success, print_warning,
    run_ssh_command
)


class Deployer:
    """Main deployment coordinator."""

    def __init__(self, config: Config, verbose: bool = False):
        """
        Initialize deployer.

        Args:
            config: Config instance
            verbose: Enable verbose output
        """
        self.config = config
        self.verbose = verbose
        self.modules = {}

    def deploy(
        self,
        skip_clash: bool = False,
        skip_autossh: bool = False,
        skip_zsh: bool = False,
        skip_web: bool = False,
        dry_run: bool = False
    ) -> bool:
        """
        Execute full deployment.

        Args:
            skip_clash: Skip Clash deployment
            skip_autossh: Skip AutoSSH deployment
            skip_zsh: Skip Zsh configuration
            skip_web: Skip Web interface deployment
            dry_run: Show what would be done without doing it

        Returns:
            True if deployment succeeds
        """
        print_info("╭─────────────────────────────────────────╮")
        print_info("│  🚀 Lab Remote Bootstrap Deployment     │")
        print_info("╰─────────────────────────────────────────╯\n")

        print_info(f"Configuration: {self.config.config_path}")
        print_info(f"Deployment mode: {self.config.deployment_mode}")

        if self.config.is_local_deployment:
            import getpass
            print_info(f"Deployment target: LOCAL (deploying on this machine)")
            print_info(f"Current user: {getpass.getuser()}\n")
        else:
            target_host = self.config.get('target.host', self.config.get('cloud.host'))
            target_user = self.config.get('target.user', self.config.get('cloud.user'))
            print_info(f"Deployment target: REMOTE (via SSH)")
            print_info(f"Target server: {target_user}@{target_host}\n")

        if dry_run:
            print_warning("DRY RUN MODE - No actual changes will be made\n")
            return self._dry_run_deploy(skip_clash, skip_autossh, skip_zsh, skip_web)

        # Phase 1: Validation
        if not self._validate_all(skip_clash, skip_autossh, skip_zsh, skip_web):
            return False

        # Phase 2: Deploy modules
        deployed_modules = []
        skipped_modules = []
        failed_modules = []

        try:
            # Deploy Clash
            if not skip_clash:
                if self._deploy_module('clash', ClashModule):
                    deployed_modules.append('clash')
                else:
                    print_error("Clash deployment failed")
                    self._rollback_modules(deployed_modules)
                    return False
            else:
                skipped_modules.append('clash')

            # Deploy AutoSSH
            if not skip_autossh:
                if self._deploy_module('autossh', AutoSSHModule):
                    deployed_modules.append('autossh')
                else:
                    print_error("AutoSSH deployment failed")
                    self._rollback_modules(deployed_modules)
                    return False
            else:
                skipped_modules.append('autossh')

            # Deploy Zsh
            if not skip_zsh:
                if self._deploy_module('zsh', ZshModule):
                    deployed_modules.append('zsh')
                else:
                    failed_modules.append('zsh')
                    print_error("Zsh deployment failed")
                    # Zsh failure is not critical, continue
                    print_warning("Continuing despite Zsh deployment failure")
            else:
                skipped_modules.append('zsh')

            # Deploy Web
            if not skip_web:
                if self._deploy_module('web', WebModule):
                    deployed_modules.append('web')
                else:
                    failed_modules.append('web')
                    print_error("Web interface deployment failed")
                    # Web failure is not critical, continue
                    print_warning("Continuing despite Web deployment failure")
            else:
                skipped_modules.append('web')

            # Phase 3: Verification
            print_info("\n[7/7] Deployment verification")
            print_info("⏳ Waiting for services to start...")
            import time
            time.sleep(5)

            from health import HealthCheck
            checker = HealthCheck(self.config)
            results = checker.run_all(check_connectivity=True)

            # Print summary
            print_info("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            if results['summary']['failed'] == 0:
                print_success("✅ Deployment completed successfully!\n")
            else:
                print_warning(f"⚠️  Deployment completed with {results['summary']['failed']} health check failures\n")

            self._print_next_steps(deployed_modules, skipped_modules, failed_modules)

            return True

        except KeyboardInterrupt:
            print_warning("\n\nDeployment interrupted by user")
            self._rollback_modules(deployed_modules)
            return False

        except Exception as e:
            print_error(f"\nDeployment failed: {e}")
            self._rollback_modules(deployed_modules)
            return False

    def _validate_all(self, skip_clash: bool, skip_autossh: bool, skip_zsh: bool, skip_web: bool = False) -> bool:
        """Validate all modules."""
        print_info("[1/7] Pre-deployment validation")

        if not self._validate_autossh_control_path(skip_autossh):
            return False

        if not self._validate_remote_sudo():
            return False

        modules_to_validate = []
        if not skip_clash:
            modules_to_validate.append(('clash', ClashModule))
        if not skip_autossh:
            modules_to_validate.append(('autossh', AutoSSHModule))
        if not skip_zsh:
            modules_to_validate.append(('zsh', ZshModule))
        if not skip_web:
            modules_to_validate.append(('web', WebModule))

        for name, module_class in modules_to_validate:
            module = module_class(self.config, self.verbose)
            self.modules[name] = module

            try:
                if not module.validate():
                    print_error(f"{name.capitalize()} validation failed")
                    return False
            except Exception as e:
                print_error(f"{name.capitalize()} validation error: {e}")
                return False

        print_success("Validation passed")
        return True

    def _validate_autossh_control_path(self, skip_autossh: bool) -> bool:
        """Reject AutoSSH redeploys that would restart the active SSH route."""
        if skip_autossh or self.config.is_local_deployment:
            return True

        target_host, _, _, target_port = self._get_remote_target_params()
        cloud_host = self.config.get('cloud.host')
        reverse_port = self.config.get('cloud.reverse_port', 2223)
        target_port = self._parse_port(target_port, "target.ssh_port")
        reverse_port = self._parse_port(reverse_port, "cloud.reverse_port")
        if target_port is None or reverse_port is None:
            return False

        target_host = self._normalize_host(target_host)
        cloud_host = self._normalize_host(cloud_host)
        if (
            target_host is not None
            and cloud_host is not None
            and target_host == cloud_host
            and target_port == reverse_port
        ):
            print_error("Unsafe remote AutoSSH deploy configuration")
            print_info(
                "The deployment SSH target uses the same host and port as "
                "cloud.reverse_port."
            )
            print_info(
                "Redeploying AutoSSH would clean or restart the reverse tunnel "
                "that is carrying this deployment connection."
            )
            print_info(
                "Use a separate target.* maintenance SSH endpoint, run deploy "
                "from the lab server with deployment.target: local, or re-run "
                "with --skip-autossh when updating only other modules."
            )
            return False

        return True

    @staticmethod
    def _normalize_host(host):
        """Normalize host strings for config endpoint comparisons."""
        if host is None:
            return None
        return str(host).strip().strip("[]").rstrip(".").lower()

    @staticmethod
    def _parse_port(value, name):
        """Parse a configured TCP port for preflight endpoint comparisons."""
        try:
            port = int(value)
        except (TypeError, ValueError):
            print_error(f"{name} must be a numeric TCP port")
            return None

        if port < 1 or port > 65535:
            print_error(f"{name} must be between 1 and 65535")
            return None

        return port

    def _validate_remote_sudo(self) -> bool:
        """Validate non-interactive sudo for remote deployments."""
        if self.config.is_local_deployment:
            return True

        host, user, identity_file, port = self._get_remote_target_params()
        self._cleanup_target_known_hosts(host, port)

        returncode, _, stderr = run_ssh_command(
            host,
            user,
            "sudo -n true",
            identity_file,
            port,
        )

        if returncode == 0:
            return True

        print_error("Remote user does not have passwordless sudo")
        if stderr:
            print_info(f"sudo check failed: {stderr.strip()}")
        print_info(
            f"Grant passwordless sudo on the target, for example: "
            f"echo '{user} ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/{user}"
        )
        return False

    def _get_remote_target_params(self):
        """Get target SSH parameters for remote deployment."""
        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')
        identity_file = self.config.get('deployment.ssh_identity_file')
        port = self.config.get('cloud.reverse_port', 2223)
        host = self.config.get('target.host', host)
        user = self.config.get('target.user', user)
        identity_file = self.config.get('target.ssh_identity_file', identity_file)
        port = self.config.get('target.ssh_port', port)
        return host, user, identity_file, port

    def _cleanup_target_known_hosts(self, host: str, port: int):
        """Remove stale known_hosts entries for the deployment target."""
        entries = [host]
        if port != 22:
            entries.append(f"[{host}]:{port}")

        for entry in entries:
            result = subprocess.run(
                ["ssh-keygen", "-R", entry],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode not in (0, 1):
                details = (result.stderr or result.stdout or "").strip()
                message = f"Could not clean known_hosts entry for {entry}"
                if details:
                    message = f"{message}: {details}"
                print_warning(message)

    def _deploy_module(self, name: str, module_class) -> bool:
        """Deploy a single module."""
        phase_names = {
            'clash': '[2/7] Clash proxy deployment',
            'autossh': '[3/7] AutoSSH tunnel deployment',
            'zsh': '[4/7] Zsh configuration deployment',
            'web': '[5/7] Web interface deployment'
        }

        print_info(f"\n{phase_names.get(name, f'{name.capitalize()} deployment')}")

        if name in self.modules:
            module = self.modules[name]
        else:
            module = module_class(self.config, self.verbose)
            self.modules[name] = module

        try:
            return module.deploy()
        except Exception as e:
            print_error(f"{name.capitalize()} deployment error: {e}")
            return False

    def _rollback_modules(self, deployed_modules: list):
        """Rollback deployed modules."""
        if not deployed_modules:
            return

        print_warning("\nRolling back deployed modules...")

        for name in reversed(deployed_modules):
            if name in self.modules:
                try:
                    self.modules[name].rollback()
                except Exception as e:
                    print_error(f"Failed to rollback {name}: {e}")

    def _dry_run_deploy(self, skip_clash: bool, skip_autossh: bool, skip_zsh: bool, skip_web: bool) -> bool:
        """Show what would be deployed without actually deploying."""
        print_info("Deployment plan:\n")

        step = 1
        if not skip_clash:
            print_info(f"[{step}/6] Clash proxy")
            print_info("  - Upload Clash binary")
            print_info("  - Upload geo data files")
            print_info("  - Upload templates")
            print_info("  - Create systemd service")
            print_info("  - Start service\n")
            step += 1

        if not skip_autossh:
            print_info(f"[{step}/6] AutoSSH tunnel")
            print_info("  - Install autossh package")
            print_info("  - Setup SSH key")
            print_info("  - Create systemd service")
            print_info("  - Start service\n")
            step += 1

        if not skip_zsh:
            print_info(f"[{step}/6] Zsh configuration")
            print_info("  - Install command-line tools (fzf, fd, eza, bat, tldr)")
            print_info("  - Install zsh plugins")
            print_info("  - Write configuration to ~/.zshrc\n")
            step += 1

        if not skip_web:
            print_info(f"[{step}/6] Web interface")
            print_info("  - Upload web application")
            print_info("  - Install Python dependencies")
            print_info("  - Create systemd service")
            print_info("  - Start service\n")
            step += 1

        print_info(f"[{step}/6] Health check")
        print_info("  - Verify services are running")
        print_info("  - Test proxy connectivity\n")

        print_success("Dry run complete")
        return True

    def _print_next_steps(self, deployed_modules=None, skipped_modules=None, failed_modules=None):
        """Print next steps based on this deployment run."""
        deployed_modules = deployed_modules or []
        skipped_modules = skipped_modules or []
        failed_modules = failed_modules or []

        reverse_port = self.config.get('cloud.reverse_port', 2223)
        cloud_host = self.config.get('cloud.host')
        lab_user = self.config.get('target.user', self.config.get('cloud.user'))
        target_host = self.config.get('target.host', cloud_host)
        target_port = self.config.get('target.ssh_port', reverse_port)
        target_identity_file = self.config.get(
            'target.ssh_identity_file',
            self.config.get('deployment.ssh_identity_file')
        )
        clash_port = self.config.get('clash.mixed_port', 7890)
        clash_controller = self.config.get('clash.external_controller', '127.0.0.1:9090')
        clash_api_port = self.config.get('clash.api_port', 9090)
        web_port = self.config.get('web.port', 5000)
        local_web_port = self.config.get('web.local_port', 5001)

        print_info("Next steps:")
        step = 1

        if failed_modules:
            print_info(f"  {step}. Review failed non-critical modules: {', '.join(failed_modules)}")
            print_info("     Re-run deploy for those modules after fixing the errors.\n")
            step += 1

        if 'autossh' in deployed_modules:
            print_info(f"  {step}. Connect to server via reverse tunnel:")
            print_info(f"     ssh -p {reverse_port} {lab_user}@{cloud_host}\n")
            step += 1

        if 'clash' in deployed_modules:
            print_info(f"  {step}. Add or update a Clash subscription:")
            print_info("     lab-remote-ctl subscription add \"Name\" https://...")
            print_info("     lab-remote-ctl subscription update \"Name\"")
            print_info(f"     Clash local proxy: 127.0.0.1:{clash_port}")
            print_info(f"     Clash controller: http://{clash_controller}\n")
            step += 1

        if 'web' in deployed_modules:
            identity_arg = f" -i {target_identity_file}" if target_identity_file else ""
            print_info(f"  {step}. Open the Web management UI through a local SSH tunnel:")
            print_info(
                f"     ssh -N -L {local_web_port}:127.0.0.1:{web_port} "
                f"-L {clash_api_port}:127.0.0.1:{clash_api_port}"
                f"{identity_arg} -p {target_port} {lab_user}@{target_host}"
            )
            print_info(f"     Web management UI: http://localhost:{local_web_port}\n")
            step += 1

        if 'zsh' in deployed_modules:
            print_info(f"  {step}. Start a new shell session to load the Zsh configuration:")
            print_info("     exec zsh -l\n")
            step += 1

        print_info(f"  {step}. Check system health:")
        print_info("     lab-remote-ctl health\n")

        if skipped_modules:
            print_info(f"Skipped this run: {', '.join(skipped_modules)}")


def deploy(
    config: Config,
    skip_clash: bool = False,
    skip_autossh: bool = False,
    skip_zsh: bool = False,
    skip_web: bool = False,
    dry_run: bool = False,
    verbose: bool = False
) -> bool:
    """
    Main deployment entry point.

    Args:
        config: Configuration instance
        skip_clash: Skip Clash deployment
        skip_autossh: Skip AutoSSH deployment
        skip_zsh: Skip Zsh configuration
        skip_web: Skip Web interface deployment
        dry_run: Show what would be done
        verbose: Enable verbose output

    Returns:
        True if deployment succeeds
    """
    deployer = Deployer(config, verbose)
    return deployer.deploy(skip_clash, skip_autossh, skip_zsh, skip_web, dry_run)
