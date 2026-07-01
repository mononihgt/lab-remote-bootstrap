#!/usr/bin/env python3
"""Base module interface for deployment modules."""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple


class BaseModule(ABC):
    """Base class for deployment modules."""

    def __init__(self, config, verbose: bool = False):
        """
        Initialize module.

        Args:
            config: Config instance
            verbose: Enable verbose output
        """
        self.config = config
        self.verbose = verbose

    @abstractmethod
    def validate(self) -> bool:
        """
        Validate prerequisites and configuration.

        Returns:
            True if validation passes

        Raises:
            Exception if validation fails
        """
        pass

    @abstractmethod
    def deploy(self) -> bool:
        """
        Execute deployment.

        Returns:
            True if deployment succeeds

        Raises:
            Exception if deployment fails
        """
        pass

    @abstractmethod
    def rollback(self) -> bool:
        """
        Rollback deployment on failure.

        Returns:
            True if rollback succeeds
        """
        pass

    def log(self, message: str):
        """Log message if verbose mode is enabled."""
        if self.verbose:
            print(f"  [DEBUG] {message}")

    def get_deployment_params(self) -> Tuple[str, str, Optional[str], int, bool]:
        """
        Get deployment parameters based on deployment target.

        Returns:
            Tuple of (host, user, identity_file, port, is_local)
        """
        is_local = self.config.is_local_deployment

        if is_local:
            # Local deployment: use localhost
            import getpass
            return (
                "localhost",
                getpass.getuser(),
                None,
                22,
                True
            )
        else:
            # Remote deployment: use cloud config
            return (
                self.config.get('cloud.host'),
                self.config.get('cloud.user'),
                self.config.get('deployment.ssh_identity_file'),
                self.config.get('cloud.reverse_port', 2223),
                False
            )
