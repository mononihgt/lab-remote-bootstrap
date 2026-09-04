# Lab Remote Bootstrap

Lab Remote Bootstrap deploys and manages a Clash proxy, an AutoSSH reverse
tunnel, a Zsh environment, and a small Web interface on a lab server.

The Python CLI supports two deployment targets:

- `local`: run directly on the lab server. The active login account is the
  deployment target user.
- `remote`: run from a controller machine and connect to the lab server through
  the explicit `target.*` SSH settings.

## Requirements

- Python 3.8 or newer for the CLI; Python 3.12 is recommended.
- `uv` is recommended on systems where the default `python3` is older than
  Python 3.8.
- A lab-server account with passwordless sudo for remote deployments and sudo
  access for local deployments.
- An SSH key on the lab server that can authenticate to the cloud account used
  by AutoSSH.

Install and run the CLI with one interpreter:

```bash
uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl --help
```

Without `uv`, bind both commands to Python 3.12:

```bash
python3.12 -m pip install -r requirements.txt
python3.12 ./cli/lab-remote-ctl --help
```

## Identity Model

The lab target account and cloud tunnel account are different settings:

| Connection | Configuration | Account used |
| --- | --- | --- |
| Controller → lab server | `target.user` | Lab-server account |
| Lab server → cloud server | `cloud.user` and `autossh.identity_file` | Cloud-server account |
| Cloud reverse listener → lab server | Derived from the target | `target.user` for remote mode, active local user for local mode |

`cloud.user` is never used as the lab-server account. For example, a local
deployment run by `labuser` publishes a listener that is entered with:

```bash
ssh -p 2224 labuser@cloud.example.com
```

Use your actual cloud host, reverse port, and lab account in real commands.

## Configuration

Start the interactive wizard:

```bash
uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl init --interactive
```

The wizard creates `config/config.yaml` and an empty
`config/subscriptions.json` using the current configuration model.

Local deployment only needs the deployment mode and cloud tunnel settings:

```yaml
deployment:
  mode: host
  target: local

cloud:
  host: <cloud_public_host>
  user: <cloud_user>
  reverse_port: 2223
  reverse_bind_address: 0.0.0.0

autossh:
  identity_file: ~/.ssh/id_ed25519_autossh
```

`autossh.identity_file` is a path on the lab server. Home-relative paths such
as `~/.ssh/id_ed25519_autossh` are expanded using the target account's home
directory for both setup commands and the systemd service.

Remote deployment requires all target fields. Target SSH keys are optional;
leave the field empty to use `~/.ssh/config` or an SSH agent:

```yaml
deployment:
  mode: host
  target: remote

target:
  host: <lab_ssh_host>
  user: <lab_user>
  ssh_port: 22
  ssh_identity_file: ~/.ssh/id_lab

cloud:
  host: <cloud_public_host>
  user: <cloud_user>
  reverse_port: 2223
  reverse_bind_address: 0.0.0.0

autossh:
  identity_file: ~/.ssh/id_ed25519_autossh
```

## Deployment

First-time setup normally runs on the lab server:

```bash
uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl deploy
```

From a controller machine, configure `deployment.target: remote` and the
complete `target` block before running the same command. Useful options:

```bash
# Preview the plan
uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl deploy --dry-run

# Update modules while preserving an existing AutoSSH tunnel
uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl deploy --skip-autossh

# Skip individual modules
uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl deploy --skip-clash --skip-zsh --skip-web
```

When a remote target uses the same host and port as the AutoSSH reverse
listener, a full AutoSSH deployment is refused to prevent the deployment SSH
connection from restarting itself. Use a separate maintenance endpoint or run
the deployment locally on the lab server.

## Subscriptions

Subscription commands default to the live deployment target. Use
`--scope workspace` to edit files in the repository before publishing them.

```bash
uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl subscription add "Primary" https://example.com/subscription

uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl subscription update "Primary"

uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl subscription list --scope workspace
```

Live files are stored under `/opt/lab-remote-stack/clash/`; workspace files
are `config/subscriptions.json` and `config/clash.generated.yaml`.

## Health and Web Interface

```bash
uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl health

uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl web start

uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl web open

uv run --python 3.12 --with-requirements requirements.txt \
  ./cli/lab-remote-ctl web stop
```

The Web service listens on the target's `127.0.0.1:5000` by default. Remote
Web access uses a local SSH tunnel on port `5001`; `web open` starts it when
needed. Clash uses HTTP port `7890`, SOCKS port `7891`, and API port `9090` by
default.

## Standalone Resources

The repository also includes independent shell resources for environments that
do not use the Python CLI:

- `cloud/prepare_cloud_reverse_ssh.sh` prepares the cloud SSH daemon.
- `host/setup_host_stack.sh` installs the host-mode stack.
- `docker/setup_docker_stack.sh` installs the Docker-mode stack.
- `local/open_clash_dashboard.sh` opens a local Clash dashboard tunnel.

These scripts use their own environment-file configuration and are separate
from the Python CLI configuration model.
