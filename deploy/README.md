# Deployment Scaffolding

This directory contains **sample deployment assets** for running `openclaw-3agent-sidecar` as a long-lived local service.

## What exists now

- `systemd/openclaw-sidecar.service` — Linux systemd example
- `systemd/openclaw-sidecar-aws-staging.service` — AWS staging-oriented Linux service example using `/home/ubuntu/openclaw-3agent-sidecar`
- `windows/openclaw-sidecar.ps1` — Windows PowerShell launcher example
- `nginx/openclaw-sidecar-aws-staging.conf` — Nginx example for publishing the new sidecar at `/sidecar/` on the current AWS host
- `aws-staging.env.example` — AWS staging candidate env template inferred from the historical OpenClaw runbook
- `aws-staging-discovery.md` — step-by-step guide for discovering `HOOKS_TOKEN`, `PUBLIC_BASE_URL`, and `RUNTIME_INVOKE_URL` on the AWS host
- `aws-staging-rollout-plan.md` — live-AWS rollout plan based on the confirmed current cloud topology
- `aws-staging-execution-checklist.md` — copyable server-side execution sequence for the first staging rollout
- `aws-staging-safe-deploy.md` — safety-first AWS deployment guide that avoids overwriting `/home/ubuntu/openclaw/.env`
- `aws-direct-cutover-impact-and-runbook.md` — direct-replacement cutover guide for replacing the legacy `127.0.0.1:9600` runtime without pretending the old Feishu/timer platform is already migrated

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
- `OPENCLAW_GATEWAY_BASE_URL`
- `OPENCLAW_HOOKS_TOKEN`
- `OPENCLAW_PUBLIC_BASE_URL`
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

For a quick end-to-end demo, you can also run:

- `openclaw-sidecar-smoke`

It launches a temporary sidecar + fake runtime pair, completes a real HTTP callback loop, and prints a JSON verification summary.

For real staging / upstream validation, run:

- `openclaw-sidecar-remote-validate`
- optional: `openclaw-sidecar-remote-validate --dispatch-sample`

`probe-only` mode checks health/readiness/ops plus upstream probe status using your configured `OPENCLAW_*` variables. `--dispatch-sample` additionally creates one sample task and attempts a real runtime submission, which is useful for staging verification but should be used intentionally because it talks to the real upstream runtime.

By default the command also reads `.env` for `OPENCLAW_*` defaults, so local staging checks work even when the shell has not explicitly exported each variable yet.

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

If you want the upstream runtime to complete a real invoke/result loop, do not stop at `OPENCLAW_RUNTIME_INVOKE_URL` alone. Also configure:

- `OPENCLAW_PUBLIC_BASE_URL` — externally reachable base URL for sidecar callbacks
- `OPENCLAW_HOOKS_TOKEN` — used to authenticate `POST /hooks/openclaw/result`

Without those callback settings, the service will correctly report integration as only partially configured, because it can submit work outward but cannot safely receive results back from the upstream runtime.

## Minimal smoke flow

After startup, verify the following in order:

1. `GET /healthz` returns `status=ok`
2. `GET /readyz` returns `status=ready`
3. `GET /ops/summary` returns:
   - `integration.status=local_only` for local-only mode, or
   - `integration.status=partially_configured|fully_configured` for integration mode
4. If `OPENCLAW_RUNTIME_INVOKE_URL` is set, confirm whether `integration.runtime_invoke.result_callback_ready` is `true`

If `result_callback_ready=false`, the first fix is usually adding `OPENCLAW_PUBLIC_BASE_URL` (and keeping `OPENCLAW_HOOKS_TOKEN` non-empty).

If you want one command instead of manual endpoint checks, run `openclaw-sidecar-smoke` and inspect the JSON summary it prints.

If you want to validate the **real** upstream instead of the fake demo runtime, run `openclaw-sidecar-remote-validate` and inspect `blocking_issues` in the JSON output.

If the runtime bridge is using `openclaw-cli://...`, prefer inspecting `blocking_issue_groups`,
`ops.integration.runtime_invoke.recent_submission`, and the CLI failure guidance in
`docs/operations-runbook.md` before diving into raw host logs.

## Next hardening steps

- rotate logs with the host process manager
- add reverse proxy or local firewall rules if needed
- back up the SQLite DB path regularly
- point `OPENCLAW_RUNTIME_INVOKE_URL` at the real OpenClaw runtime invoke endpoint
