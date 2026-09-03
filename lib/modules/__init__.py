#!/usr/bin/env python3
"""Base module interface for deployment modules."""

from abc import ABC, abstractmethod
from deployment import DeploymentContext


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
        self.context = DeploymentContext.from_config(config)

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
