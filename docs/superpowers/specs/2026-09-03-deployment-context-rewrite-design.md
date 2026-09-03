# Deployment Context Rewrite Design

## Scope

Rewrite the Python CLI orchestration core (`cli/`, `lib/`, tests, and README).
Keep the standalone `host/`, `docker/`, and `cloud/` shell scripts unchanged.

## Problem

Target endpoint resolution is duplicated across the deployer, modules, health
checks, subscription storage, and CLI commands. Several copies use
`cloud.user` as a fallback for `target.user`, conflating the cloud account used
by AutoSSH with the lab account used to access the reverse tunnel. Local
deployments have no configured target account, so status output may advertise
the cloud account for an SSH endpoint that reaches the local lab host.

## Model

`DeploymentContext` is the only module that resolves target identity and
transport. It contains two explicit values:

- `target`: the machine where deployment commands, files, services, and health
  checks execute. A local target resolves to the active local login user. A
  remote target requires all `target.host`, `target.user`, and
  `target.ssh_port` fields.
- `cloud_tunnel`: the cloud SSH endpoint used solely by AutoSSH to publish the
  reverse listener. Its user always comes from `cloud.user`.

The context hides local-vs-SSH details behind `run`, `upload`, and `download`.
It also produces target and reverse-tunnel SSH command arguments for CLI/UI
callers. Callers do not inspect `target.*` or `cloud.*` to choose a user.

## Invariants

- `cloud.user` never identifies the lab target or reverse-tunnel client login.
- A local reverse-tunnel login uses the active local login user.
- A remote reverse-tunnel login uses `target.user`.
- Remote configurations with incomplete `target.*` fields fail before any SSH
  command is attempted.
- `autossh.identity_file` remains a key on the lab target for the outbound
  lab-to-cloud connection; it is not a controller SSH identity.

## Migration

This is a clean break. Local configurations remain valid without a `target`
block. Remote configurations must include `target.host`, `target.user`, and
`target.ssh_port`. The deprecated `deployment.ssh_identity_file`, cloud
endpoint fallback, `migrate` CLI command, and migration module are removed.
The Python CLI supports only this configuration model.

## Verification

Tests cover context resolution, local and remote command routing, correct
reverse-tunnel username output, target validation, Web tunnel arguments,
health checks, subscription live-store access, and module deployment routing.
The full suite and compile check run after the rewrite.
