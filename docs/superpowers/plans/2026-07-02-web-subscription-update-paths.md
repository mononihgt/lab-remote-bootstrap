# Web Subscription Update Paths Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Web subscription update API read and write deployed runtime subscription files, then verify a real subscription can be downloaded and converted without touching live user state.

**Architecture:** Add a focused shared resolver in `lib/subscription_paths.py` so CLI and Web path behavior is explicit instead of duplicated. The CLI keeps its existing local-project behavior for remote deployments, while the deployed Web app always uses `clash.install_root` runtime files.

**Tech Stack:** Python 3.7+, Click CLI, Flask Web API, `unittest`, `requests`, `PyYAML`.

## Global Constraints

- Do not change remote deploy tunnel behavior.
- Do not redesign the Web UI.
- Do not change subscription storage format.
- Do not write the provided subscription URL into committed files.
- Keep the remote deploy port-disconnect README TODO.
- Remove or mark fixed only the Web subscription update README TODO after verification.

---

### Task 1: Shared Subscription Path Resolver

**Files:**
- Create: `lib/subscription_paths.py`
- Modify: `cli/lab-remote-ctl`
- Modify: `tests/test_cli_init.py`
- Test: `tests/test_subscription_paths.py`

**Interfaces:**
- Produces: `SubscriptionPaths(subscriptions_file: pathlib.Path, config_file: pathlib.Path)`
- Produces: `resolve_subscription_paths(config, project_root: Optional[pathlib.Path] = None, runtime_context: str = "cli") -> SubscriptionPaths`
- Consumes: `config.is_remote_deployment` and `config.get("clash.install_root", "/opt/lab-remote-stack")`

- [ ] **Step 1: Write failing tests for shared resolver**

Create `tests/test_subscription_paths.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
    def __init__(self, remote=True, install_root="/tmp/lab-stack"):
        self.is_remote_deployment = remote
        self.install_root = install_root

    def get(self, key_path, default=None):
        if key_path == "clash.install_root":
            return self.install_root
        return default


class SubscriptionPathTests(unittest.TestCase):
    def test_cli_remote_context_uses_project_config_files(self):
        from subscription_paths import resolve_subscription_paths

        with tempfile.TemporaryDirectory() as root:
            project_root = Path(root)
            paths = resolve_subscription_paths(
                FakeConfig(remote=True, install_root="/opt/lab-remote-stack"),
                project_root=project_root,
                runtime_context="cli",
            )

        self.assertEqual(paths.subscriptions_file, project_root / "config" / "subscriptions.json")
        self.assertEqual(paths.config_file, project_root / "config" / "clash.generated.yaml")

    def test_cli_local_context_uses_install_root_files(self):
        from subscription_paths import resolve_subscription_paths

        paths = resolve_subscription_paths(
            FakeConfig(remote=False, install_root="/tmp/lab-stack"),
            project_root=PROJECT_ROOT,
            runtime_context="cli",
        )

        self.assertEqual(paths.subscriptions_file, Path("/tmp/lab-stack/clash/subscriptions.json"))
        self.assertEqual(paths.config_file, Path("/tmp/lab-stack/clash/config.yaml"))

    def test_web_context_uses_install_root_even_for_remote_deployment(self):
        from subscription_paths import resolve_subscription_paths

        paths = resolve_subscription_paths(
            FakeConfig(remote=True, install_root="/opt/lab-remote-stack"),
            project_root=PROJECT_ROOT,
            runtime_context="web",
        )

        self.assertEqual(paths.subscriptions_file, Path("/opt/lab-remote-stack/clash/subscriptions.json"))
        self.assertEqual(paths.config_file, Path("/opt/lab-remote-stack/clash/config.yaml"))

    def test_unknown_runtime_context_fails_fast(self):
        from subscription_paths import resolve_subscription_paths

        with self.assertRaisesRegex(ValueError, "Unknown subscription runtime context"):
            resolve_subscription_paths(FakeConfig(), runtime_context="worker")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run resolver tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_subscription_paths -v
```

Expected: FAIL because `subscription_paths` does not exist.

- [ ] **Step 3: Implement the shared resolver**

Create `lib/subscription_paths.py`:

```python
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
```

- [ ] **Step 4: Update CLI to use the shared resolver**

In `cli/lab-remote-ctl`, remove the local `SubscriptionPaths` dataclass and `resolve_subscription_paths` function. Add this import near the other local library imports:

```python
from subscription_paths import SubscriptionPaths, resolve_subscription_paths
```

Keep all existing CLI command calls to `resolve_subscription_paths(config)` unchanged.

- [ ] **Step 5: Run resolver and existing CLI path tests**

Run:

```bash
python3 -m unittest tests.test_subscription_paths tests.test_cli_init -v
```

Expected: PASS.

- [ ] **Step 6: Commit shared resolver**

Run:

```bash
git add lib/subscription_paths.py cli/lab-remote-ctl tests/test_subscription_paths.py tests/test_cli_init.py
git commit -m "Share subscription path resolution"
```

---

### Task 2: Web Runtime Path Wiring

**Files:**
- Modify: `web/app.py`
- Modify: `tests/test_web_module.py`
- Test: `tests/test_web_app_paths.py`

**Interfaces:**
- Consumes: `resolve_subscription_paths(config, project_root=project_root, runtime_context="web")`
- Produces: module globals in `web/app.py`: `subscriptions_file: str`, `config_file: str`

- [ ] **Step 1: Write failing Web path test**

Create `tests/test_web_app_paths.py`:

```python
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_DIR = PROJECT_ROOT / "lib"
sys.path.insert(0, str(LIB_DIR))


class FakeConfig:
    is_remote_deployment = True

    def get(self, key_path, default=None):
        values = {
            "clash.install_root": "/tmp/lab-web-runtime",
            "web.bind": "127.0.0.1",
            "clash.api_port": 9090,
        }
        return values.get(key_path, default)


class WebAppPathTests(unittest.TestCase):
    def test_web_app_uses_runtime_subscription_paths(self):
        app_path = PROJECT_ROOT / "web" / "app.py"
        spec = importlib.util.spec_from_file_location("web_app_paths_test", app_path)
        module = importlib.util.module_from_spec(spec)

        with patch("config.load_config", return_value=FakeConfig()):
            sys.modules["web_app_paths_test"] = module
            spec.loader.exec_module(module)

        self.assertEqual(module.subscriptions_file, "/tmp/lab-web-runtime/clash/subscriptions.json")
        self.assertEqual(module.config_file, "/tmp/lab-web-runtime/clash/config.yaml")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run Web path test and verify it fails**

Run:

```bash
python3 -m unittest tests.test_web_app_paths -v
```

Expected before implementation: FAIL if Web still computes paths directly or does not import the shared resolver.

- [ ] **Step 3: Update Web app to use shared resolver**

In `web/app.py`, add the import:

```python
from subscription_paths import resolve_subscription_paths
```

Replace:

```python
install_root = config.get('clash.install_root', '/opt/lab-remote-stack')
subscriptions_file = f"{install_root}/clash/subscriptions.json"
config_file = f"{install_root}/clash/config.yaml"
```

with:

```python
install_root = config.get('clash.install_root', '/opt/lab-remote-stack')
project_root = Path(__file__).parent.parent
subscription_paths = resolve_subscription_paths(
    config,
    project_root=project_root,
    runtime_context="web",
)
subscriptions_file = str(subscription_paths.subscriptions_file)
config_file = str(subscription_paths.config_file)
```

Remove the later duplicate `project_root = Path(__file__).parent.parent` assignment and keep:

```python
template_dir = str(project_root / "assets" / "clash" / "templates")
```

- [ ] **Step 4: Ensure Web deployment uploads the new runtime module**

In `lib/modules/web_module.py`, extend `runtime_modules`:

```python
runtime_modules = ["config.py", "subscription.py", "subscription_paths.py", "health.py", "utils.py"]
```

Update `tests/test_web_module.py` so its fixture creates `subscription_paths.py` and its expected upload list includes:

```python
"/opt/lab-remote-stack/lib/subscription_paths.py",
```

- [ ] **Step 5: Run Web tests**

Run:

```bash
python3 -m unittest tests.test_web_app_paths tests.test_web_module -v
```

Expected: PASS.

- [ ] **Step 6: Commit Web wiring**

Run:

```bash
git add web/app.py lib/modules/web_module.py tests/test_web_app_paths.py tests/test_web_module.py
git commit -m "Use runtime subscription paths in web app"
```

---

### Task 3: Real Subscription Verification and README Cleanup

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `Subscription.update(name: str, template_dir: str, output_file: str) -> Tuple[str, int]`
- Consumes: temporary `subscriptions.json` created outside the repo

- [ ] **Step 1: Run full unit suite before real network verification**

Run:

```bash
python3 -m unittest discover tests -v
```

Expected: PASS.

- [ ] **Step 2: Verify real subscription update in a temporary directory**

Run:

```bash
tmpdir="$(mktemp -d)"
printf 'Subscription URL: ' >&2
IFS= read -r SUBSCRIPTION_URL
export SUBSCRIPTION_URL
python3 - "$tmpdir" <<'PY'
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "lib"))
from subscription import Subscription

tmpdir = Path(sys.argv[1])
subscriptions_file = tmpdir / "subscriptions.json"
output_file = tmpdir / "config.yaml"
subscription_url = os.environ.get("SUBSCRIPTION_URL")
if not subscription_url:
    raise SystemExit("SUBSCRIPTION_URL is required")

subscriptions_file.write_text(json.dumps({
    "version": "1.0",
    "active": "Verification",
    "subscriptions": [{
        "name": "Verification",
        "url": subscription_url,
        "type": None,
        "template": "balanced",
        "added_at": "2026-07-02T00:00:00Z",
        "last_update": None,
        "node_count": 0,
        "status": "active",
    }],
}, indent=2))

manager = Subscription(str(subscriptions_file))
sub_type, node_count = manager.update(
    "Verification",
    str(Path.cwd() / "assets" / "clash" / "templates"),
    str(output_file),
)

if node_count <= 0:
    raise SystemExit(f"node_count must be > 0, got {node_count}")
if not output_file.exists():
    raise SystemExit("generated config.yaml was not created")

print(f"type={sub_type}")
print(f"node_count={node_count}")
print(f"output={output_file}")
PY
```

When prompted, paste the subscription URL from the original task. Expected: exit code 0, output includes `node_count=` with a value greater than 0.

- [ ] **Step 3: Confirm subscription URL is not in committed files**

Run:

```bash
printf 'Subscription URL: ' >&2
IFS= read -r SUBSCRIPTION_URL
test -n "$SUBSCRIPTION_URL"
git grep --fixed-strings -- "$SUBSCRIPTION_URL"
```

Expected: no output and exit code 1.

- [ ] **Step 4: Update README TODO list**

In `README.md`, replace:

```markdown
## 待完善功能

- [ ] 当使用云服务器对局域网服务器进行remote deploy时，会因为使用同一个端口而导致链接断开，无法进行后续deploy
- [ ] web管理界面添加订阅后，无法正常下载订阅文件，也无法update
```

with:

```markdown
## 待完善功能

- [ ] 当使用云服务器对局域网服务器进行remote deploy时，会因为使用同一个端口而导致链接断开，无法进行后续deploy
```

- [ ] **Step 5: Run final checks**

Run:

```bash
python3 -m unittest discover tests -v
git diff --check
git status --short
```

Expected: tests PASS, `git diff --check` has no output, and `git status --short` only lists intentional implementation and README files.

- [ ] **Step 6: Commit verification and README cleanup**

Run:

```bash
git add README.md
git commit -m "Document fixed web subscription update"
```
