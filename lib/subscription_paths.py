#!/usr/bin/env python3
"""Subscription state and generated Clash config path resolution."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class SubscriptionPaths:
    """Resolved paths for subscription state and generated Clash config."""

    subscriptions_file: Path
    config_file: Path


def resolve_subscription_paths(
    config,
    project_root: Optional[Path] = None,
    runtime_context: str = "cli",
) -> SubscriptionPaths:
    """Resolve subscription storage paths for CLI or deployed Web runtime."""
    if runtime_context not in {"cli", "web"}:
        raise ValueError(f"Unknown subscription runtime context: {runtime_context}")

    if runtime_context == "cli" and config.is_remote_deployment:
        root = project_root or Path(__file__).resolve().parents[1]
        return SubscriptionPaths(
            subscriptions_file=root / "config" / "subscriptions.json",
            config_file=root / "config" / "clash.generated.yaml",
        )

    install_root = config.get("clash.install_root", "/opt/lab-remote-stack")
    return SubscriptionPaths(
        subscriptions_file=Path(install_root) / "clash" / "subscriptions.json",
        config_file=Path(install_root) / "clash" / "config.yaml",
    )
