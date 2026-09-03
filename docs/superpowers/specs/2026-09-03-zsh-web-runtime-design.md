# Zsh Installation and Web Runtime Design

## Problem

On a lab host with system Python 3.6.9, deployment reports successful Zsh and
Web modules even though neither is usable. The Zsh module installs optional
tools but omits the `zsh` package itself. The Web module installs dependencies
with `python3 -m pip ... || true`, hides installation errors, and writes a
systemd service that hard-codes `/usr/bin/python3`. Flask 3 requires Python
3.8+, so the Python 3.6 service exits immediately.

## Goals

- Install and verify the required `zsh` executable before configuring plugins
  or telling the user to run `exec zsh -l`.
- Run the deployed Web service in an isolated, persistent Python 3.12 virtual
  environment instead of the host's unsupported system Python.
- Surface dependency-setup failures as deployment failures with useful stderr.
- Preserve remote and local deployment transport behavior.

## Design

### Zsh module

The package-manager-specific Zsh tool lists include `zsh` as a required first
package. After best-effort installation, the module checks `command -v zsh`.
If Zsh cannot be installed, deployment fails before plugins or `.zshrc` are
written. Optional tools remain best effort.

### Web module

The Web module uploads the workspace `requirements.txt` to its deployed Web
directory. During dependency setup it creates or updates
`<install_root>/web/.venv` using `uv venv --python 3.12` when `uv` is available.
It installs from the deployed requirements file through that venv's Python.

If `uv` is unavailable, the module uses an installed `python3.12` executable.
If neither is present, it fails clearly instead of falling back to an
unsupported `python3`. The systemd `ExecStart` uses the venv interpreter, so
the service runs independently of shell activation and `uv`'s transient run
environment.

### Error handling

- A missing Zsh package is a hard module failure, with the package-manager
  command's error visible to the user.
- Web dependency setup does not suppress failures; the module returns failure
  and prints the relevant stderr.
- Existing Web service status failures continue to point users to
  `journalctl`, where Python application failures remain visible.

## Testing

- Add Zsh module tests that require `zsh` in the APT install command and
  reject a missing `zsh` executable.
- Add Web module tests that verify requirements are uploaded, a Python 3.12
  venv is created with `uv`, dependencies install through the venv interpreter,
  and systemd uses the venv executable.
- Run focused Zsh/Web tests, the full test suite, and the compile check.
