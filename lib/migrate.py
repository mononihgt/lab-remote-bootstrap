#!/usr/bin/env python3
"""Configuration migration from old .env format to new config.yaml format."""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


class MigrationError(Exception):
    """Migration related errors."""
    pass


class EnvMigrator:
    """Migrate old .env configuration to new config.yaml format."""

    # Mapping from old env keys to new YAML paths
    ENV_MAPPING = {
        'CLOUD_HOST': 'cloud.host',
        'CLOUD_USER': 'cloud.user',
        'REVERSE_PORT': 'cloud.reverse_port',
        'INSTALL_ROOT': 'clash.install_root',
        'CLASH_HTTP_PORT': 'clash.http_port',
        'CLASH_SOCKS_PORT': 'clash.socks_port',
        'CLASH_API_PORT': 'clash.api_port',
        'CLASH_CONFIG_URL': 'subscription.url',  # Special handling needed
        'AUTOSSH_IDENTITY_FILE': 'autossh.identity_file',
        'AUTOSSH_MONITOR_PORT': 'autossh.monitor_port',
        'CONTAINER_NAME': 'docker.container_name',
        'CONTAINER_ROOT_PASSWORD': 'docker.root_password',
        'HOST_SSH_PORT': 'docker.host_ssh_port',
    }

    def __init__(self, env_file: str):
        """
        Initialize migrator.

        Args:
            env_file: Path to .env file
        """
        self.env_file = Path(env_file).expanduser().resolve()
        if not self.env_file.exists():
            raise MigrationError(f"Environment file not found: {self.env_file}")

        self.env_data: Dict[str, str] = {}
        self.config_data: Dict[str, Any] = {}
        self.subscription_url: Optional[str] = None
        self.mode: str = 'host'
        self.migration_report: List[Tuple[str, str, str]] = []

    def parse_env_file(self) -> Dict[str, str]:
        """
        Parse .env file into dictionary.

        Returns:
            Dictionary of environment variables
        """
        env_data = {}

        try:
            with open(self.env_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()

                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue

                    # Parse KEY=value or KEY="value"
                    match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', line)
                    if match:
                        key, value = match.groups()

                        # Remove surrounding quotes if present
                        value = value.strip()
                        if (value.startswith('"') and value.endswith('"')) or \
                           (value.startswith("'") and value.endswith("'")):
                            value = value[1:-1]

                        env_data[key] = value
                    else:
                        # Invalid line format, skip
                        continue

        except Exception as e:
            raise MigrationError(f"Failed to parse env file: {e}")

        return env_data

    def detect_mode(self) -> str:
        """
        Detect deployment mode from environment file path or variables.

        Returns:
            'host' or 'docker'
        """
        # Check file path for mode hints
        file_path_lower = str(self.env_file).lower()
        if 'docker' in file_path_lower:
            return 'docker'
        elif 'host' in file_path_lower:
            return 'host'

        # Check for docker-specific variables
        docker_keys = {'CONTAINER_NAME', 'CONTAINER_ROOT_PASSWORD', 'HOST_SSH_PORT'}
        if any(key in self.env_data for key in docker_keys):
            return 'docker'

        # Default to host mode
        return 'host'

    def expand_path(self, path: str) -> str:
        """
        Expand ~ to home directory in path.

        Args:
            path: Path string

        Returns:
            Expanded path string
        """
        if path.startswith('~'):
            return os.path.expanduser(path)
        return path

    def convert_value(self, key: str, value: str) -> Any:
        """
        Convert string value to appropriate type.

        Args:
            key: Environment key
            value: String value

        Returns:
            Converted value (int, bool, or string)
        """
        # Port numbers should be integers
        if 'PORT' in key:
            try:
                return int(value)
            except ValueError:
                return value

        # File paths should be expanded
        if 'FILE' in key or 'ROOT' in key:
            return self.expand_path(value)

        return value

    def set_nested_value(self, config: Dict[str, Any], key_path: str, value: Any):
        """
        Set value in nested dictionary using dot-separated key path.

        Args:
            config: Configuration dictionary
            key_path: Dot-separated key path (e.g., 'cloud.host')
            value: Value to set
        """
        keys = key_path.split('.')
        current = config

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def migrate(self) -> Dict[str, Any]:
        """
        Perform migration from .env to config.yaml structure.

        Returns:
            Configuration dictionary in new format
        """
        # Parse env file
        self.env_data = self.parse_env_file()

        # Detect deployment mode
        self.mode = self.detect_mode()

        # Initialize config structure with defaults
        self.config_data = {
            'deployment': {
                'mode': self.mode
            },
            'cloud': {},
            'clash': {
                'subscription': {
                    'template': 'balanced',
                    'auto_update': False,
                    'update_interval': 86400
                }
            },
            'autossh': {},
            'zsh': {
                'enable_plugins': True,
                'custom_config': {
                    'autosuggestions_style': 'fg=240',
                    'fzf_theme': {
                        'fg': '#CBE0F0',
                        'bg': '#011628',
                        'bg_highlight': '#143652',
                        'purple': '#B388FF',
                        'blue': '#06BCE4',
                        'cyan': '#2CF9ED'
                    },
                    'bat_theme': 'tokyonight_night',
                    'eza_aliases': True,
                    'tldr_alias': True,
                    'fastfetch_on_startup': True
                }
            },
            'web': {
                'enabled': True,
                'port': 5000,
                'bind': '127.0.0.1'
            }
        }

        # Add docker section if in docker mode
        if self.mode == 'docker':
            self.config_data['docker'] = {
                'target_user': 'developer'
            }

        # Migrate environment variables
        for env_key, yaml_path in self.ENV_MAPPING.items():
            if env_key in self.env_data:
                value = self.env_data[env_key]
                converted_value = self.convert_value(env_key, value)

                # Special handling for CLASH_CONFIG_URL
                if env_key == 'CLASH_CONFIG_URL':
                    self.subscription_url = value
                    self.migration_report.append((
                        env_key,
                        'subscriptions.json',
                        f'Will create subscription "Default" with URL'
                    ))
                else:
                    self.set_nested_value(self.config_data, yaml_path, converted_value)
                    self.migration_report.append((env_key, yaml_path, str(converted_value)))

        # Handle unmapped variables (report them)
        unmapped = set(self.env_data.keys()) - set(self.ENV_MAPPING.keys())
        for key in unmapped:
            self.migration_report.append((
                key,
                'SKIPPED',
                f'Not mapped (value: {self.env_data[key]})'
            ))

        return self.config_data

    def generate_config_yaml(self, output_path: Optional[str] = None) -> str:
        """
        Generate config.yaml content.

        Args:
            output_path: Optional path to write config to

        Returns:
            YAML content as string
        """
        yaml_content = yaml.dump(
            self.config_data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True
        )

        # Add header comment
        header = f"""# Lab Remote Bootstrap Configuration
# Migrated from: {self.env_file}
# Migration date: {self._get_timestamp()}

"""
        full_content = header + yaml_content

        if output_path:
            output_file = Path(output_path).expanduser().resolve()
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w') as f:
                f.write(full_content)

        return full_content

    def generate_subscriptions_json(self, output_path: Optional[str] = None) -> Optional[str]:
        """
        Generate subscriptions.json if CLASH_CONFIG_URL was present.

        Args:
            output_path: Optional path to write subscriptions.json to

        Returns:
            JSON content as string, or None if no subscription URL
        """
        if not self.subscription_url:
            return None

        subscriptions_data = {
            'version': '1.0',
            'active': 'Default',
            'subscriptions': [
                {
                    'name': 'Default',
                    'url': self.subscription_url,
                    'type': None,
                    'template': 'balanced',
                    'added_at': self._get_timestamp(),
                    'last_update': None,
                    'node_count': 0,
                    'status': 'active'
                }
            ]
        }

        json_content = json.dumps(subscriptions_data, indent=2, ensure_ascii=False)

        if output_path:
            output_file = Path(output_path).expanduser().resolve()
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with open(output_file, 'w') as f:
                f.write(json_content)

        return json_content

    def get_migration_report(self) -> str:
        """
        Generate human-readable migration report.

        Returns:
            Formatted migration report
        """
        report_lines = [
            "Migration Report",
            "=" * 80,
            f"Source: {self.env_file}",
            f"Detected mode: {self.mode}",
            "",
            "Variable Mapping:",
            "-" * 80,
        ]

        # Group by status
        migrated = [r for r in self.migration_report if r[1] not in ('SKIPPED', 'subscriptions.json')]
        subscription = [r for r in self.migration_report if r[1] == 'subscriptions.json']
        skipped = [r for r in self.migration_report if r[1] == 'SKIPPED']

        if migrated:
            report_lines.append("\nMigrated to config.yaml:")
            for env_key, yaml_path, value in migrated:
                report_lines.append(f"  {env_key:30s} -> {yaml_path:30s} = {value}")

        if subscription:
            report_lines.append("\nSubscription URL:")
            for env_key, target, description in subscription:
                report_lines.append(f"  {env_key:30s} -> {description}")
                report_lines.append(f"  {'':30s}    URL: {self.subscription_url}")

        if skipped:
            report_lines.append("\nSkipped (not mapped):")
            for env_key, _, description in skipped:
                report_lines.append(f"  {env_key:30s} -> {description}")

        report_lines.extend([
            "",
            "-" * 80,
            f"Total variables processed: {len(self.env_data)}",
            f"  Migrated to config.yaml: {len(migrated)}",
            f"  Migrated to subscriptions: {len(subscription)}",
            f"  Skipped: {len(skipped)}",
            ""
        ])

        return "\n".join(report_lines)

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"


def migrate_env_to_yaml(
    env_file: str,
    config_output: Optional[str] = None,
    subscriptions_output: Optional[str] = None,
    dry_run: bool = False
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], str]:
    """
    Migrate .env file to config.yaml format.

    Args:
        env_file: Path to .env file
        config_output: Optional path to write config.yaml
        subscriptions_output: Optional path to write subscriptions.json
        dry_run: If True, don't write files

    Returns:
        Tuple of (config_dict, subscriptions_dict, report_string)
    """
    migrator = EnvMigrator(env_file)

    # Perform migration
    config_data = migrator.migrate()

    # Generate outputs
    if not dry_run:
        migrator.generate_config_yaml(config_output)
        migrator.generate_subscriptions_json(subscriptions_output)

    # Get report
    report = migrator.get_migration_report()

    # Get subscription data if present
    subscriptions_data = None
    if migrator.subscription_url:
        subscriptions_json = migrator.generate_subscriptions_json()
        if subscriptions_json:
            subscriptions_data = json.loads(subscriptions_json)

    return config_data, subscriptions_data, report
