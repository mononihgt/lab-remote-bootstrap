# Target Cloud Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split deployment target SSH settings from cloud tunnel settings and let interactive init optionally seed a VPN subscription URL.

**Architecture:** Add a `target` config section for local-to-lab SSH while keeping `cloud` for lab-to-cloud AutoSSH. Keep compatibility fallbacks for existing configs. Add small tests around config routing and wizard output.

**Tech Stack:** Python 3, Click, YAML/JSON schema, unittest.

---

### Task 1: Config Routing

**Files:**
- Modify: `lib/modules/__init__.py`
- Modify: `lib/deployer.py`
- Modify: `cli/lab-remote-ctl`
- Test: `tests/test_deployment_identity_split.py`
- Test: `tests/test_deployer_preflight.py`

- [ ] Add failing tests proving remote deployment uses `target.host`, `target.user`, `target.ssh_port`, and `target.ssh_identity_file`.
- [ ] Add failing tests proving compatibility fallback still reads old `cloud.*` and `deployment.ssh_identity_file`.
- [ ] Update `BaseModule.get_deployment_params()` to prefer `target.*` and fall back to old fields.
- [ ] Update sudo preflight and web start/stop to use the same target params.
- [ ] Run `python3 -m unittest tests/test_deployment_identity_split.py tests/test_deployer_preflight.py`.

### Task 2: Interactive Init Output

**Files:**
- Modify: `cli/lab-remote-ctl`
- Test: `tests/test_cli_init.py`

- [ ] Add failing CliRunner tests for remote interactive init that writes separate `target` and `cloud` sections.
- [ ] Add failing CliRunner test for optional VPN URL that creates a local `subscriptions.json`.
- [ ] Refactor config generation into helper functions that can be tested without running a full terminal session.
- [ ] Update interactive prompts to ask target lab server host/user/port/key, then cloud public host/user/reverse port, then optional VPN subscription URL.
- [ ] Run `python3 -m unittest tests/test_cli_init.py`.

### Task 3: Schema, Example, README

**Files:**
- Modify: `config/config.schema.json`
- Modify: `config/config.example.yaml`
- Modify: `README.md`

- [ ] Add `target` schema and example fields.
- [ ] Keep existing `deployment.ssh_identity_file` accepted for compatibility, but document `target.ssh_identity_file` as preferred.
- [ ] Update README topology and wizard guidance with the local Mac, lab server, and cloud server roles.
- [ ] Run `./cli/lab-remote-ctl --help` and `./cli/lab-remote-ctl deploy --dry-run`.

### Task 4: Verification and Commit

**Files:**
- All changed files.

- [ ] Run `python3 -m unittest discover -s tests`.
- [ ] Run `env PYTHONPYCACHEPREFIX=.pycache_tmp python3 -m compileall cli lib tests`.
- [ ] Remove `.pycache_tmp`.
- [ ] Check `git diff --stat`.
- [ ] Commit with `git commit -m "Clarify target and cloud configuration"`.
