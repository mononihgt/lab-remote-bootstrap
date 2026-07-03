#!/usr/bin/env python3
"""Subscription file storage for workspace and live targets."""

import tempfile
import shlex
from pathlib import Path
from typing import Optional, Tuple

from subscription_paths import SubscriptionPaths, resolve_subscription_paths
from utils import download_file, run_ssh_command, upload_file


class SubscriptionStoreError(Exception):
    """Subscription storage operation failed."""


class SubscriptionStore:
    """Prepare subscription files for CLI operations and sync changes back."""

    def __init__(self, config, scope: str = "live", project_root: Optional[Path] = None):
        self.config = config
        self.scope = scope
        self.project_root = project_root
        self.remote_paths = resolve_subscription_paths(
            config,
            project_root=project_root,
            runtime_context="cli",
            scope=scope,
        )
        self.local_paths = self.remote_paths
        self._tempdir = None
        self._remote_live = scope == "live" and config.is_remote_deployment

    def prepare(self):
        """Make subscription files available locally for the operation."""
        if not self._remote_live:
            return self

        self._tempdir = tempfile.TemporaryDirectory()
        temp_root = Path(self._tempdir.name)
        self.local_paths = SubscriptionPaths(
            subscriptions_file=temp_root / "subscriptions.json",
            config_file=temp_root / "config.yaml",
        )

        if self._remote_file_exists(str(self.remote_paths.subscriptions_file)):
            if not self._download(str(self.remote_paths.subscriptions_file), str(self.local_paths.subscriptions_file)):
                raise SubscriptionStoreError(
                    f"Failed to download remote subscriptions: {self.remote_paths.subscriptions_file}"
                )

        return self

    def sync(self, upload_config: bool = False):
        """Upload local changes back to the live target when needed."""
        if not self._remote_live:
            return

        self._ensure_remote_dir(str(self.remote_paths.subscriptions_file.parent))

        if self.local_paths.subscriptions_file.exists():
            if not self._upload(
                str(self.local_paths.subscriptions_file),
                str(self.remote_paths.subscriptions_file),
            ):
                raise SubscriptionStoreError(
                    f"Failed to upload remote subscriptions: {self.remote_paths.subscriptions_file}"
                )

        if upload_config and self.local_paths.config_file.exists():
            if not self._upload(
                str(self.local_paths.config_file),
                str(self.remote_paths.config_file),
            ):
                raise SubscriptionStoreError(
                    f"Failed to upload remote Clash config: {self.remote_paths.config_file}"
                )

    def cleanup(self):
        """Remove local temporary files."""
        if self._tempdir:
            self._tempdir.cleanup()
            self._tempdir = None

    def _target_params(self) -> Tuple[str, str, Optional[str], int]:
        host = self.config.get('cloud.host')
        user = self.config.get('cloud.user')
        identity_file = self.config.get('deployment.ssh_identity_file')
        port = self.config.get('cloud.reverse_port', 2223)
        host = self.config.get('target.host', host)
        user = self.config.get('target.user', user)
        identity_file = self.config.get('target.ssh_identity_file', identity_file)
        port = self.config.get('target.ssh_port', port)
        return host, user, identity_file, port

    def _remote_file_exists(self, remote_path: str) -> bool:
        host, user, identity_file, port = self._target_params()
        returncode, _, _ = run_ssh_command(
            host,
            user,
            f"test -f {shlex.quote(remote_path)}",
            identity_file,
            port,
        )
        return returncode == 0

    def _ensure_remote_dir(self, remote_dir: str):
        host, user, identity_file, port = self._target_params()
        returncode, _, stderr = run_ssh_command(
            host,
            user,
            f"mkdir -p {shlex.quote(remote_dir)}",
            identity_file,
            port,
        )
        if returncode != 0:
            raise SubscriptionStoreError(f"Failed to create remote directory {remote_dir}: {stderr}")

    def _download(self, remote_path: str, local_path: str) -> bool:
        host, user, identity_file, port = self._target_params()
        return download_file(remote_path, local_path, host, user, identity_file, port)

    def _upload(self, local_path: str, remote_path: str) -> bool:
        host, user, identity_file, port = self._target_params()
        return upload_file(local_path, remote_path, host, user, identity_file, port)
