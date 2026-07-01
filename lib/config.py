#!/usr/bin/env python3
"""Configuration management for lab-remote-bootstrap."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigError(Exception):
    """Configuration related errors."""
    pass


class Config:
    """Configuration manager for lab-remote-bootstrap."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to config.yaml file. If None, searches in default locations.
        """
        self.config_path = self._find_config(config_path)
        self.data: Dict[str, Any] = {}
        self.schema: Dict[str, Any] = {}
        self._load_schema()
        if self.config_path:
            self._load_config()
            self._validate()

    def _find_config(self, config_path: Optional[str]) -> Optional[Path]:
        """Find configuration file."""
        if config_path:
            path = Path(config_path).expanduser().resolve()
            if not path.exists():
                raise ConfigError(f"Config file not found: {path}")
            return path

        # Search in default locations
        search_paths = [
            Path.cwd() / "config" / "config.yaml",
            Path.cwd() / "config.yaml",
            Path.home() / ".config" / "lab-remote-bootstrap" / "config.yaml",
        ]

        for path in search_paths:
            if path.exists():
                return path

        return None

    def _load_schema(self):
        """Load JSON schema for validation."""
        schema_path = Path(__file__).parent.parent / "config" / "config.schema.json"
        if schema_path.exists():
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)

    def _load_config(self):
        """Load configuration from YAML file."""
        if not self.config_path:
            raise ConfigError("No configuration file specified")

        try:
            with open(self.config_path, 'r') as f:
                self.data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load config: {e}")

    def _validate(self):
        """Validate configuration against schema."""
        if not self.schema:
            return

        try:
            import jsonschema
            jsonschema.validate(instance=self.data, schema=self.schema)
        except ImportError:
            # jsonschema not installed, skip validation
            pass
        except Exception as e:
            raise ConfigError(f"Configuration validation failed: {e}")

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-separated key path.

        Args:
            key_path: Dot-separated key path (e.g., 'clash.http_port')
            default: Default value if key not found

        Returns:
            Configuration value
        """
        keys = key_path.split('.')
        value = self.data

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any):
        """
        Set configuration value by dot-separated key path.

        Args:
            key_path: Dot-separated key path
            value: Value to set
        """
        keys = key_path.split('.')
        current = self.data

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def save(self, path: Optional[str] = None):
        """
        Save configuration to file.

        Args:
            path: Path to save to. If None, uses current config_path.
        """
        save_path = Path(path) if path else self.config_path
        if not save_path:
            raise ConfigError("No path specified for saving configuration")

        save_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(save_path, 'w') as f:
                yaml.dump(self.data, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise ConfigError(f"Failed to save config: {e}")

    @property
    def deployment_mode(self) -> str:
        """Get deployment mode."""
        return self.get('deployment.mode', 'host')

    @property
    def deployment_target(self) -> str:
        """Get deployment target (local or remote)."""
        return self.get('deployment.target', 'remote')

    @property
    def is_local_deployment(self) -> bool:
        """Check if deploying on local machine."""
        return self.deployment_target == 'local'

    @property
    def is_remote_deployment(self) -> bool:
        """Check if deploying via SSH."""
        return self.deployment_target == 'remote'

    @property
    def is_docker_mode(self) -> bool:
        """Check if deployment mode is docker."""
        return self.deployment_mode == 'docker'

    @property
    def is_host_mode(self) -> bool:
        """Check if deployment mode is host."""
        return self.deployment_mode == 'host'


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from file.

    Args:
        config_path: Path to config file

    Returns:
        Config instance
    """
    return Config(config_path)
