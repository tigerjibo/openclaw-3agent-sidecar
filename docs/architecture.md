# Architecture

`openclaw-3agent-sidecar` is an orchestration layer built on top of the official OpenClaw runtime.

## Layers

1. Official OpenClaw: gateway, routing, skills, webhook, agent runtime
2. Sidecar kernel: tasks, task_events, state machine, API, projections
3. Sidecar runtime: dispatcher, scheduler, recovery, role health
4. Adapter layer: ingress, invoke, result contracts (planned)

## Current migrated foundation

The current repository already contains the reusable prototype kernel foundation:

- storage
- models
- events
- state machine
- runtime mode controller
- local HTTP control plane
- projection/detail/metrics foundation

## Current adapter foundation

The minimal adapter loop is now implemented:

- ingress adapter: normalize institutional task input into the task kernel
- agent invoke adapter: build stable role invoke payloads
- result adapter: write structured role output back into the kernel and advance state

## Current runtime foundation

The minimal runtime loop is now implemented and has entered the first observable / recoverable stage:

- dispatcher: pick the next role for a task and mark dispatch in-flight
- scheduler: recover in-flight dispatches after restart and dispatch ready tasks
- result consumption clears in-flight dispatch state so the next role can continue
- recovery: release stale in-flight dispatches, detect execution / review timeouts, and escalate blocked tasks
- role health: produce per-role running / degraded snapshots and feed service health payloads

The runtime control plane now also includes integration-aware service semantics:

- gateway hook auto-registration state
- maintenance-driven registration retry with backoff window
- integration-aware operator guidance and intervention summary
- readiness blocking when repeated upstream registration failures exceed the configured threshold

## External storytelling vs runtime truth

For product communication, the same 3-agent runtime can be framed as a **Ming-style small cabinet**:

- user = Emperor
- `coordinator` = Chief Grand Secretary / 首辅
- `executor` = Grand Secretary / 大学士
- `reviewer` = Supervising Reviewer / 监审官

This framing must remain outside the runtime source of truth. Code, APIs, tests, and storage continue to use canonical role ids: `coordinator`, `executor`, and `reviewer`.

## Persistence boundary

Only **task** and **task_event** rows in SQLite survive restarts. All other `ServiceRunner` state is ephemeral and rebuilt automatically:

| State | Persisted? | Recovery strategy |
| ----- | ---------- | ----------------- |
| `tasks` table | Yes | Survives restart as-is |
| `task_events` table | Yes | Survives restart as-is |
| `dispatch_status=running` tasks | Yes (in DB) | `TaskRecovery.recover_inflight_dispatches()` resets to idle |
| `_maintenance_history` | No | Rebuilt after first maintenance cycle |
| `_integration_probe_cache` | No | Rebuilt on next probe interval |
| `_hook_registration_state` | No | Re-attempted during `start()` |
| `lifecycle_state` | No | Set to "ready" during `start()` |

This boundary is intentional: operational telemetry is cheap to re-derive, while task truth must be durable.

## Operations handoff

For day-2 operations, see `docs/operations-runbook.md`.
