# Task 2 Report: Web Runtime Path Wiring

## What I changed

- Updated `web/app.py` to import `resolve_subscription_paths(...)` from `lib/subscription_paths.py` and resolve:
  - `subscriptions_file`
  - `config_file`
  using `project_root=Path(__file__).parent.parent` and `runtime_context="web"`.
- Kept the shared `project_root` for template resolution and removed the duplicate assignment.
- Updated `lib/modules/web_module.py` so Web runtime deployment uploads `subscription_paths.py` alongside the other required runtime library modules.
- Added `tests/test_web_app_paths.py`:
  - the brief-specified path-value assertion;
  - an explicit wiring test proving `web/app.py` calls `resolve_subscription_paths(..., runtime_context="web")`.
- Updated `tests/test_web_module.py` so its fixture creates `subscription_paths.py` and its expected runtime upload list includes `/opt/lab-remote-stack/lib/subscription_paths.py`.
- Updated `README.md` to mark the Web subscription update TODO as fixed while leaving the remote deploy port-disconnect TODO unchanged.

## TDD notes

- I first added the brief-specified `tests/test_web_app_paths.py` and ran `python3 -m unittest tests.test_web_app_paths -v`.
- That test passed immediately because the old direct path concatenation happened to produce the same runtime paths, so it did not prove the required wiring.
- I then added a narrower failing test in the same file that patches `subscription_paths.resolve_subscription_paths` and asserts the Web app calls it with `runtime_context="web"`. That test failed before production changes and passed afterward.

## Verification

- Focused RED:
  - `python3 -m unittest tests.test_web_app_paths -v`
    - initially failed once the wiring assertion was added.
- Focused GREEN:
  - `python3 -m unittest tests.test_web_app_paths tests.test_web_module -v`
- Full suite:
  - `python3 -m unittest discover -s tests -p 'test*.py' -v`

All listed test runs passed after the implementation.

## Commit

- `12d9750` - `Use runtime subscription paths in web app`

## Concerns

- The repository’s default `python3 -m unittest -v` discovers `0` tests here; the actual full-suite command for this repo/worktree is `python3 -m unittest discover -s tests -p 'test*.py' -v`.

## Task 2 follow-up fix

- Restored the Web subscription update TODO in `README.md` so Task 3 can remove it only after real verification.
- Kept the remote deploy port-disconnect TODO unchanged.
- Removed the redundant `install_root` local in `web/app.py` by reading the config value inline in `/api/config`, which preserves the response payload without leaving a dead assignment behind.

## Verification for this fix

- Command: `python3 -m unittest tests.test_web_app_paths tests.test_web_module -v`
- Result: `Ran 4 tests in 2.170s` and `OK`
- Notes: the run emitted an existing `urllib3`/LibreSSL warning and the expected Web service log lines from `tests.test_web_module`, but the test process exited successfully.
