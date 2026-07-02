# Web Subscription Update Paths Design

Date: 2026-07-02

## Context

`README.md` lists a TODO that the Web management interface can add a subscription, but cannot download or update it. The CLI already has remote-aware subscription path handling, while `web/app.py` currently derives subscription and generated Clash config paths directly from `clash.install_root`.

The approved scope is limited to the Web subscription download/update issue. The separate TODO about remote deploy disconnecting when a cloud reverse tunnel reuses the same port remains out of scope.

## Goal

Make Web subscription update use the same runtime files that the deployed Clash service uses, then verify that a real subscription URL can be downloaded and converted into a Clash config without modifying the user's live subscription state.

## Non-Goals

- Do not change remote deploy tunnel behavior.
- Do not redesign the Web UI.
- Do not change subscription storage format.
- Do not write the provided subscription URL into committed files.

## Design

Add a small shared module for subscription path resolution:

- `lib/subscription_paths.py`
- `SubscriptionPaths`
- `resolve_subscription_paths(config, project_root=None, runtime_context="cli")`

The shared resolver has two contexts:

- `runtime_context="cli"` preserves the current CLI behavior:
  - remote deployment uses local project files:
    - `config/subscriptions.json`
    - `config/clash.generated.yaml`
  - local deployment uses `clash.install_root` runtime files:
    - `<install_root>/clash/subscriptions.json`
    - `<install_root>/clash/config.yaml`
- `runtime_context="web"` always uses runtime files under `clash.install_root`, because the Web service runs on the deployed machine and should update the files Clash actually reads.

Update `cli/lab-remote-ctl` to import the shared resolver instead of owning its own duplicate implementation.

Update `web/app.py` to call the shared resolver with `runtime_context="web"` and use the returned paths for all subscription API actions.

## Data Flow

1. The Web API receives `POST /api/subscriptions/<name>/update`.
2. `web/app.py` creates `Subscription(subscriptions_file)` using the runtime subscriptions path.
3. `Subscription.update(...)` downloads the subscription URL, detects the format, generates or accepts Clash YAML, and writes the runtime Clash config path.
4. The subscriptions JSON is saved with `last_update`, `type`, and `node_count`.

## Error Handling

Existing error behavior remains:

- download failures return a JSON error with HTTP 500 from the Web API;
- unknown subscription formats raise `SubscriptionError`;
- missing templates raise `SubscriptionError`;
- failed file writes raise `SubscriptionError`.

The resolver rejects unknown runtime contexts with `ValueError` so caller mistakes fail early.

## Testing

Add focused unit coverage:

- CLI context keeps the existing remote/local path behavior.
- Web context uses `clash.install_root` even when `deployment.target` is `remote`.
- `web/app.py` path selection is covered without starting Flask or touching live runtime files.

Run the existing unit test suite after changes.

For the real subscription URL verification, create a temporary subscriptions file with one active subscription pointing at the provided URL, call `Subscription.update(...)` with the existing Clash templates and a temporary output config path, then verify:

- the update succeeds;
- a generated Clash YAML file exists;
- node count is greater than zero;
- no committed config or subscription file contains the subscription URL.

## Documentation

Update the README TODO list after verification:

- keep the remote deploy port-disconnect TODO;
- remove or mark fixed the Web subscription update TODO.

