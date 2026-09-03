#!/usr/bin/env python3
"""Utility functions for lab-remote-bootstrap."""

import getpass
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

MIN_SUPPORTED_PYTHON = (3, 8)


def check_python_version(version_info=None) -> Tuple[bool, str]:
    """Return whether the running interpreter meets project requirements."""
    version_info = version_info or sys.version_info
    if isinstance(version_info, tuple):
        major, minor = version_info[:2]
        micro = version_info[2] if len(version_info) > 2 else 0
    else:
        major = version_info.major
        minor = version_info.minor
        micro = getattr(version_info, 'micro', 0)
    current = f"{major}.{minor}.{micro}"
    minimum = ".".join(str(part) for part in MIN_SUPPORTED_PYTHON)
    if (major, minor) < MIN_SUPPORTED_PYTHON:
        return (
            False,
            f"Python {current} is not supported; Python {minimum}+ is required. "
            f"Use the intended interpreter explicitly, for example: "
            f"python3.12 -m pip install -r requirements.txt",
        )
    return True, current


def is_local_endpoint(host: str, user: str) -> bool:
    """Return whether legacy transport parameters identify this local user."""
    return host in {"localhost", "127.0.0.1", "::1"} and user == getpass.getuser()


def run_command(
    cmd: List[str],
    check: bool = True,
    capture_output: bool = False,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
) -> Tuple[int, str, str]:
    """
    Run a shell command.

    Args:
        cmd: Command and arguments as list
        check: Raise exception on non-zero exit code
        capture_output: Capture stdout and stderr
        cwd: Working directory
        env: Environment variables

    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            cwd=cwd,
            env=env,
        )
        return result.returncode, result.stdout or "", result.stderr or ""
    except subprocess.CalledProcessError as e:
        return e.returncode, e.stdout or "", e.stderr or ""
    except Exception as e:
        return 1, "", str(e)


def run_ssh_command(
    host: str,
    user: str,
    cmd: str,
    identity_file: Optional[str] = None,
    port: int = 22,
    local: Optional[bool] = None,
) -> Tuple[int, str, str]:
    """
    Run command on remote host via SSH, or locally if local=True.

    Args:
        host: Remote hostname
        user: SSH user
        cmd: Command to execute
        identity_file: Path to SSH private key
        port: SSH port
        local: If True, run command locally instead of via SSH

    Returns:
        Tuple of (returncode, stdout, stderr)
    """
    # Local deployments use the canonical localhost parameters returned by
    # BaseModule. Infer that transport when callers use the legacy signature.
    if local is None:
        local = is_local_endpoint(host, user)

    if local:
        # Run command locally using bash
        return run_command(["bash", "-c", cmd], check=False, capture_output=True)

    ssh_cmd = ["ssh"]

    if identity_file:
        identity_file = os.path.expanduser(identity_file)
        ssh_cmd.extend(["-i", identity_file])

    ssh_cmd.extend([
        "-p", str(port),
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        f"{user}@{host}",
        cmd
    ])

    return run_command(ssh_cmd, check=False, capture_output=True)


def upload_file(
    local_path: str,
    remote_path: str,
    host: str,
    user: str,
    identity_file: Optional[str] = None,
    port: int = 22,
    local: Optional[bool] = None,
) -> bool:
    """
    Upload file to remote host via SCP, or copy locally if local=True.

    Args:
        local_path: Local file path
        remote_path: Remote file path
        host: Remote hostname
        user: SSH user
        identity_file: Path to SSH private key
        port: SSH port
        local: If True, copy file locally instead of via SCP

    Returns:
        True if successful
    """
    if local is None:
        local = is_local_endpoint(host, user)

    if local:
        # Copy file locally
        import shutil
        try:
            Path(remote_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, remote_path)
            return True
        except Exception as e:
            print_error(f"Failed to copy file: {e}")
            return False

    scp_cmd = ["scp"]

    if identity_file:
        identity_file = os.path.expanduser(identity_file)
        scp_cmd.extend(["-i", identity_file])

    scp_cmd.extend([
        "-P", str(port),
        "-o", "StrictHostKeyChecking=accept-new",
        local_path,
        f"{user}@{host}:{remote_path}"
    ])

    returncode, _, _ = run_command(scp_cmd, check=False, capture_output=True)
    return returncode == 0


def download_file(
    remote_path: str,
    local_path: str,
    host: str,
    user: str,
    identity_file: Optional[str] = None,
    port: int = 22,
    local: Optional[bool] = None,
) -> bool:
    """
    Download file from remote host via SCP, or copy locally if local=True.

    Args:
        remote_path: Remote file path
        local_path: Local file path
        host: Remote hostname
        user: SSH user
        identity_file: Path to SSH private key
        port: SSH port
        local: If True, copy file locally instead of via SCP

    Returns:
        True if successful
    """
    if local is None:
        local = is_local_endpoint(host, user)

    if local:
        import shutil
        try:
            Path(local_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(remote_path, local_path)
            return True
        except Exception as e:
            print_error(f"Failed to copy file: {e}")
            return False

    Path(local_path).parent.mkdir(parents=True, exist_ok=True)

    scp_cmd = ["scp"]

    if identity_file:
        identity_file = os.path.expanduser(identity_file)
        scp_cmd.extend(["-i", identity_file])

    scp_cmd.extend([
        "-P", str(port),
        "-o", "StrictHostKeyChecking=accept-new",
        f"{user}@{host}:{remote_path}",
        local_path,
    ])

    returncode, _, _ = run_command(scp_cmd, check=False, capture_output=True)
    return returncode == 0


def expand_path(path: str) -> Path:
    """
    Expand user home and resolve path.

    Args:
        path: Path string

    Returns:
        Resolved Path object
    """
    return Path(path).expanduser().resolve()


def ensure_dir(path: str) -> Path:
    """
    Ensure directory exists.

    Args:
        path: Directory path

    Returns:
        Path object
    """
    p = expand_path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_file(path: str) -> str:
    """
    Read file contents.

    Args:
        path: File path

    Returns:
        File contents as string
    """
    p = expand_path(path)
    with open(p, 'r') as f:
        return f.read()


def write_file(path: str, content: str):
    """
    Write content to file.

    Args:
        path: File path
        content: Content to write
    """
    p = expand_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w') as f:
        f.write(content)


def check_command_exists(command: str) -> bool:
    """
    Check if command exists in PATH.

    Args:
        command: Command name

    Returns:
        True if command exists
    """
    returncode, _, _ = run_command(["which", command], check=False, capture_output=True)
    return returncode == 0


def get_project_root() -> Path:
    """
    Get project root directory.

    Returns:
        Project root path
    """
    # Assume this file is at lib/utils.py
    return Path(__file__).parent.parent.resolve()


def print_success(message: str):
    """Print success message in green."""
    print(f"\033[32m✓\033[0m {message}")


def print_error(message: str):
    """Print error message in red."""
    print(f"\033[31m✗\033[0m {message}", file=sys.stderr)


def print_warning(message: str):
    """Print warning message in yellow."""
    print(f"\033[33m⚠\033[0m {message}")


def print_info(message: str):
    """Print info message in blue."""
    print(f"\033[34mℹ\033[0m {message}")
