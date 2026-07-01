#!/usr/bin/env python3
"""Main deployment coordinator."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from modules.clash_module import ClashModule
from modules.autossh_module import AutoSSHModule
from modules.zsh_module import ZshModule
from modules.web_module import WebModule
from utils import print_error, print_info, print_success, print_warning


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
            print_info(f"Deployment target: REMOTE (via SSH)")
            print_info(f"Target server: {self.config.get('cloud.user')}@{self.config.get('cloud.host')}\n")

        if dry_run:
            print_warning("DRY RUN MODE - No actual changes will be made\n")
            return self._dry_run_deploy(skip_clash, skip_autossh, skip_zsh, skip_web)

        # Phase 1: Validation
        if not self._validate_all(skip_clash, skip_autossh, skip_zsh, skip_web):
            return False

        # Phase 2: Deploy modules
        deployed_modules = []

        try:
            # Deploy Clash
            if not skip_clash:
                if self._deploy_module('clash', ClashModule):
                    deployed_modules.append('clash')
                else:
                    print_error("Clash deployment failed")
                    self._rollback_modules(deployed_modules)
                    return False

            # Deploy AutoSSH
            if not skip_autossh:
                if self._deploy_module('autossh', AutoSSHModule):
                    deployed_modules.append('autossh')
                else:
                    print_error("AutoSSH deployment failed")
                    self._rollback_modules(deployed_modules)
                    return False

            # Deploy Zsh
            if not skip_zsh:
                if self._deploy_module('zsh', ZshModule):
                    deployed_modules.append('zsh')
                else:
                    print_error("Zsh deployment failed")
                    # Zsh failure is not critical, continue
                    print_warning("Continuing despite Zsh deployment failure")

            # Deploy Web
            if not skip_web:
                if self._deploy_module('web', WebModule):
                    deployed_modules.append('web')
                else:
                    print_error("Web interface deployment failed")
                    # Web failure is not critical, continue
                    print_warning("Continuing despite Web deployment failure")

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

            self._print_next_steps()

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

    def _print_next_steps(self):
        """Print next steps after deployment."""
        reverse_port = self.config.get('cloud.reverse_port', 2223)
        cloud_host = self.config.get('cloud.host')
        cloud_user = self.config.get('cloud.user')

        print_info("Next steps:")
        print_info(f"  1. Connect to server via reverse tunnel:")
        print_info(f"     ssh -p {reverse_port} {cloud_user}@{cloud_host}\n")
        print_info(f"  2. Add a Clash subscription:")
        print_info(f"     lab-remote-ctl subscription add \"Name\" https://...\n")
        print_info(f"  3. Update the subscription:")
        print_info(f"     lab-remote-ctl subscription update \"Name\"\n")
        print_info(f"  4. Check system health:")
        print_info(f"     lab-remote-ctl health\n")


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
