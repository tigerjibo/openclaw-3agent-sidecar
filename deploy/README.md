# Deployment Scaffolding

This directory contains **sample deployment assets** for running `openclaw-3agent-sidecar` as a long-lived local service.

## What exists now

- `systemd/openclaw-sidecar.service` — Linux systemd example
- `windows/openclaw-sidecar.ps1` — Windows PowerShell launcher example

These files are intentionally lightweight and should be adapted for your environment.

## Recommended environment variables

Prefer the canonical `OPENCLAW_*` variables:

- `OPENCLAW_HOST`
- `OPENCLAW_PORT`
- `OPENCLAW_DB_PATH`
- `OPENCLAW_MAINTENANCE_INTERVAL_SEC`
- `OPENCLAW_EXECUTING_TIMEOUT_SEC`
- `OPENCLAW_REVIEWING_TIMEOUT_SEC`
- `OPENCLAW_BLOCKED_ALERT_AFTER_SEC`
- `OPENCLAW_DEFAULT_RUNTIME_MODE`
- `OPENCLAW_RUNTIME_INVOKE_URL`
- `OPENCLAW_INTEGRATION_PROBE_TTL_SEC`
- `OPENCLAW_LOG_LEVEL`

Legacy aliases still supported for compatibility:

- `SIDECAR_DB_PATH`
- `SIDECAR_LOG_LEVEL`

## Start command

After installing the package, you can start the service with:

- `openclaw-sidecar`

Or directly with Python:

- `python -m sidecar`

## Suggested directory layout

- `./data/sidecar.db` — SQLite persistence
- `./logs/` — service logs
- `./.env` — runtime configuration

## Health and ops endpoints

Once the service is running, the local control plane exposes:

- `/healthz`
- `/readyz`
- `/runtime/maintenance`
- `/ops/summary`

`/healthz` and `/ops/summary` now also include integration probe summaries for upstream gateway hooks and runtime invoke wiring, which helps distinguish “configured but unreachable” from true local-only mode.

Those probe summaries are cached and include a `probed_at` timestamp. Normal reads reuse the last probe result, maintenance cycles refresh the cache, and `OPENCLAW_INTEGRATION_PROBE_TTL_SEC` defines how long a cached probe can be reused before the control plane re-checks upstream integrations on demand.

Probe component payloads may also expose a structured `reason` field—such as `network_error`, `http_4xx`, `http_5xx`, `probe_error`, or `probe_exception`—to distinguish transport failures from upstream HTTP behavior.

## Next hardening steps

- rotate logs with the host process manager
- add reverse proxy or local firewall rules if needed
- back up the SQLite DB path regularly
- point `OPENCLAW_RUNTIME_INVOKE_URL` at the real OpenClaw runtime invoke endpoint
