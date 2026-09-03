# Local Deployment and Python Runtime Design

## Problem

`deployment.target: local` currently sends module commands to `user@localhost`
over SSH. System commands then invoke `sudo` in a non-interactive SSH session,
so a normal sudo password cannot be entered and deployment fails with
`sudo: no tty present and no askpass program specified`. Separately,
`pip3 install -r requirements.txt` can resolve to an older system Python (for
example Python 3.6), even when a Python 3.12 environment is available. Modern
dependencies such as `rich>=13` do not support that interpreter.

## Goals

- Make local deployment execute commands and file transfers directly on the
  current machine rather than through SSH to localhost.
- Prompt for the local sudo password interactively once per deployment, then
  rely on the sudo credential cache for subsequent commands.
- Preserve existing remote SSH behavior and its passwordless-sudo preflight.
- Reject unsupported Python runtimes clearly and document an interpreter-bound
  dependency installation command.
- Keep the change covered by focused unit tests and update user documentation.

## Design

### Target execution

`run_ssh_command` and `upload_file` remain the common module interfaces. Their
local path is selected by each module from `get_deployment_params()` and runs
the command with the local shell or copies the file with `shutil`, without an
SSH process. The local deployer performs `sudo -v` through an interactive
subprocess before module execution. A failed prompt stops preflight with an
actionable error. Remote deployment continues to use `sudo -n true` and never
prompts for a remote password.

All module calls pass the existing `is_local` value so Clash, AutoSSH, Zsh,
and Web share identical transport semantics. Local paths therefore work for
uploads, systemd setup, service control, and health checks.

### Python runtime and dependencies

The CLI checks that its running interpreter is a supported Python version
(Python 3.8 or newer, matching the project’s documented compatibility). The
check emits the actual executable/version and recommends running
`python3.12 -m pip install -r requirements.txt` (or the active environment’s
`python -m pip`) when an older `pip3` is selected. Requirements retain modern
minimums; they are not downgraded to accommodate Python 3.6.

README setup instructions state that the same interpreter used to run
`lab-remote-ctl` must install requirements, and include a quick version check.

## Error handling

- Local sudo authentication failures identify the command (`sudo -v`) and tell
  the user to verify sudo access or run the command from a terminal.
- Local command failures preserve the command’s stderr in the existing module
  error messages.
- Unsupported Python versions fail before importing optional runtime
  dependencies, with an upgrade/venv remediation hint.

## Testing

- Unit-test local command execution and local file-copy behavior without
  spawning SSH.
- Unit-test deployer local sudo preflight success and failure paths.
- Preserve existing remote preflight and module tests.
- Add CLI/runtime tests for supported and unsupported interpreter diagnostics.
- Run the focused unit tests, then the full test suite and compile check.
