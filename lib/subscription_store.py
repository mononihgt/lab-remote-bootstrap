#!/usr/bin/env python3
"""Subscription file storage for workspace and live targets."""

import tempfile
import shlex
from pathlib import Path
from typing import Optional

from deployment import DeploymentContext
from subscription_paths import SubscriptionPaths, resolve_subscription_paths


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
        self.context = DeploymentContext.from_config(config) if self._remote_live else None

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

    def _remote_file_exists(self, remote_path: str) -> bool:
        returncode, _, _ = self.context.run(f"test -f {shlex.quote(remote_path)}")
        return returncode == 0

    def _ensure_remote_dir(self, remote_dir: str):
        returncode, _, stderr = self.context.run(f"mkdir -p {shlex.quote(remote_dir)}")
        if returncode != 0:
            raise SubscriptionStoreError(f"Failed to create remote directory {remote_dir}: {stderr}")

    def _download(self, remote_path: str, local_path: str) -> bool:
        return self.context.download(remote_path, local_path)

    def _upload(self, local_path: str, remote_path: str) -> bool:
        return self.context.upload(local_path, remote_path)
