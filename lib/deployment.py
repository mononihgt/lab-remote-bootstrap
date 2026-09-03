#!/usr/bin/env python3
"""Resolved deployment target and cloud tunnel transport."""

from __future__ import annotations

import getpass
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from utils import download_file, run_command, run_ssh_command, upload_file


class DeploymentConfigurationError(ValueError):
    """The deployment target configuration is incomplete or invalid."""


@dataclass(frozen=True)
class TargetEndpoint:
    """Machine on which deployment operations run."""

    host: Optional[str]
    user: str
    ssh_port: int
    identity_file: Optional[str]
    is_local: bool

    @property
    def destination(self) -> str:
        """Return the SSH destination for a remote target."""
        if self.is_local or not self.host:
            raise DeploymentConfigurationError("A local target has no SSH destination")
        return f"{self.user}@{self.host}"


@dataclass(frozen=True)
class CloudTunnel:
    """Cloud account that receives the AutoSSH reverse listener."""

    host: str
    user: str
    reverse_port: int
    reverse_bind_address: str


class DeploymentContext:
    """Resolve deployment identity once and route target operations safely.

    ``target`` and ``cloud_tunnel`` are deliberately separate: commands that
    operate on the lab machine use ``target``; only the AutoSSH outbound
    connection uses ``cloud_tunnel``.
    """

    def __init__(self, target: TargetEndpoint, cloud_tunnel: CloudTunnel):
        self.target = target
        self.cloud_tunnel = cloud_tunnel

    @classmethod
    def from_config(cls, config) -> "DeploymentContext":
        """Create a context without inferring target data from cloud settings."""
        target_name = config.get("deployment.target", "remote")
        if target_name == "local":
            target = TargetEndpoint(
                host=None,
                user=getpass.getuser(),
                ssh_port=22,
                identity_file=None,
                is_local=True,
            )
        elif target_name == "remote":
            host = cls._required_text(config, "target.host")
            user = cls._required_text(config, "target.user")
            target = TargetEndpoint(
                host=host,
                user=user,
                ssh_port=cls._port(config.get("target.ssh_port"), "target.ssh_port"),
                identity_file=cls._optional_text(config.get("target.ssh_identity_file")),
                is_local=False,
            )
        else:
            raise DeploymentConfigurationError(
                "deployment.target must be either 'local' or 'remote'"
            )

        cloud_tunnel = CloudTunnel(
            host=cls._required_text(config, "cloud.host"),
            user=cls._required_text(config, "cloud.user"),
            reverse_port=cls._port(
                config.get("cloud.reverse_port", 2223), "cloud.reverse_port"
            ),
            reverse_bind_address=cls._optional_text(
                config.get("cloud.reverse_bind_address")
            )
            or "0.0.0.0",
        )
        return cls(target=target, cloud_tunnel=cloud_tunnel)

    @staticmethod
    def _required_text(config, path: str) -> str:
        value = config.get(path)
        if isinstance(value, str) and value.strip():
            return value.strip()
        raise DeploymentConfigurationError(f"{path} must be configured")

    @staticmethod
    def _optional_text(value) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _port(value, path: str) -> int:
        if isinstance(value, bool):
            raise DeploymentConfigurationError(f"{path} must be a numeric TCP port")
        try:
            port = int(value)
        except (TypeError, ValueError) as exc:
            raise DeploymentConfigurationError(
                f"{path} must be a numeric TCP port"
            ) from exc
        if not 1 <= port <= 65535:
            raise DeploymentConfigurationError(f"{path} must be between 1 and 65535")
        return port

    def run(self, command: str) -> Tuple[int, str, str]:
        """Run a shell command on the resolved deployment target."""
        if self.target.is_local:
            return run_command(["bash", "-c", command], check=False, capture_output=True)
        return run_ssh_command(
            self.target.host,
            self.target.user,
            command,
            self.target.identity_file,
            self.target.ssh_port,
        )

    def upload(self, local_path: str, target_path: str) -> bool:
        """Copy a local file to the resolved deployment target."""
        if self.target.is_local:
            try:
                Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_path, target_path)
                return True
            except OSError:
                return False
        return upload_file(
            local_path,
            target_path,
            self.target.host,
            self.target.user,
            self.target.identity_file,
            self.target.ssh_port,
        )

    def download(self, target_path: str, local_path: str) -> bool:
        """Copy a file from the resolved deployment target."""
        if self.target.is_local:
            try:
                Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target_path, local_path)
                return True
            except OSError:
                return False
        return download_file(
            target_path,
            local_path,
            self.target.host,
            self.target.user,
            self.target.identity_file,
            self.target.ssh_port,
        )

    def target_ssh_args(self, *arguments: str) -> List[str]:
        """Build an SSH command to the configured remote deployment target."""
        if self.target.is_local:
            raise DeploymentConfigurationError("A local target does not use SSH")
        args = ["ssh", *arguments]
        if self.target.identity_file:
            args.extend(["-i", os.path.expanduser(self.target.identity_file)])
        args.extend(["-p", str(self.target.ssh_port), self.target.destination])
        return args

    def reverse_tunnel_ssh_args(self) -> List[str]:
        """Build the operator command that enters the lab through AutoSSH."""
        return [
            "ssh",
            "-p",
            str(self.cloud_tunnel.reverse_port),
            f"{self.target.user}@{self.cloud_tunnel.host}",
        ]
