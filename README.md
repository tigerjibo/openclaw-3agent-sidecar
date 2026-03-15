# OpenClaw 3-Agent Sidecar

A lightweight 3-agent orchestration sidecar built on top of the official `openclaw/openclaw` runtime.

> **Small Cabinet, Serious Delivery.**
>
> Not a room full of agents talking past each other. A compact 3-role cabinet where one role plans, one role delivers, and one role says “not good enough” when quality is not there.

一个更适合中文语境的说法是：

> **小内阁，大协作。**
>
> 皇帝下旨，首辅统筹，大学士承办，监审官把关。

## At a glance

`openclaw-3agent-sidecar` is for teams who want AI collaboration to behave more like a **delivery system** and less like an unstructured group chat.

It is built around four ideas:

- **three fixed roles** instead of role explosion
- **sidecar task truth** instead of scattered chat history as pseudo-state
- **review independent from execution** instead of self-certification
- **recovery and health built into runtime** instead of manual guesswork after failure

## External positioning

`openclaw-3agent-sidecar` can be introduced externally as a **Ming-style small cabinet for AI collaboration**:

- **Emperor** — the user / task issuer
- **Chief Grand Secretary** — `coordinator`, responsible for intake, planning, and orchestration
- **Grand Secretary** — `executor`, responsible for execution and evidence-backed delivery
- **Supervising Reviewer** — `reviewer`, responsible for independent review and rejection / approval

In Chinese-facing materials, the same framing can be expressed as:

- **皇帝**：用户 / 下发任务者
- **首辅**：统筹、拆解、推进，对应 `coordinator`
- **大学士**：承办、执行、提交证据，对应 `executor`
- **监审官**：独立审议、封驳返工、质量把关，对应 `reviewer`

### Why this framing works

Because this project is intentionally **small, constrained, and accountable**:

- not a free-form agent group chat
- not a bloated 12-role bureaucracy
- not a fork of official OpenClaw
- but a lightweight orchestration sidecar with clear separation of planning, execution, and review

The canonical runtime roles, APIs, and tests remain `coordinator / executor / reviewer`. The historical framing is for product communication only and must not replace the runtime source of truth.

## Why 3 roles, not 12?

Because this project is intentionally optimizing for the **smallest serious institution** that can still deliver accountable AI work.

Three roles are enough to create real separation of responsibility:

- **`coordinator` / 首辅** — receives the task, clarifies the goal, defines the acceptance bar
- **`executor` / 大学士** — does the work, produces outputs, and returns evidence
- **`reviewer` / 监审官** — independently judges whether the work is good enough or should go back for rework

More roles can create richer theater, but they also increase configuration, coordination cost, and coupling.

Our current design principle is simple:

> **Don’t add more roles until the 3-role kernel stops being enough.**

## Positioning

This repository is **not** an OpenClaw fork and does **not** modify official OpenClaw source code.

It acts as a sidecar orchestration layer that provides:

- task kernel (`tasks` + `task_events`)
- 3-agent state machine (`coordinator / executor / reviewer`)
- externally brandable role framing (`Chief Grand Secretary / Grand Secretary / Supervising Reviewer`)
- dispatch / review / rework flow
- recovery + role health foundation
- projection / detail / metrics surfaces
- adapters for integrating with the official OpenClaw gateway

## What already exists today

The project already has a meaningful kernel foundation in place:

- task kernel (`tasks`, `task_events`)
- stable 3-role state machine
- ingress / invoke / result adapter loop
- dispatcher + scheduler runtime loop
- recovery foundation
- role health foundation
- service health integration
- tests covering adapter / runtime baseline behavior

So while the product shell is still light, this is **not** a documentation-only repository.

## Why not just let multiple agents “self-organize”?

Because unrestricted collaboration often produces:

- unclear ownership
- weak review discipline
- difficult recovery after stalls or restarts
- chat transcripts instead of task truth

This repository takes the opposite approach:

- a **single sidecar task truth source**
- a **fixed 3-role state machine**
- **review that is structurally independent from execution**
- **recovery and role health** as runtime responsibilities rather than afterthoughts

In short: fewer roles, clearer contracts, stronger delivery discipline.

## How we differ from heavier systems

Some multi-agent products scale by adding:

- more departments
- more dashboards
- more ceremony
- more coordination paths

We are deliberately taking a narrower path:

- a smaller cabinet, not a larger bureaucracy
- a kernel-first sidecar, not a UI-first orchestration shell
- a single task truth source, not multiple quasi-canonical operational views
- a runtime that can recover and explain itself, not one that only looks impressive in demos

That is our strategic trade-off:

> **less spectacle, more clarity; fewer roles, stronger accountability.**

## Messaging snippets

Use these when introducing the project externally:

- **One-line positioning**: A lightweight 3-Agent sidecar for OpenClaw that turns AI collaboration into a recoverable, reviewable delivery workflow.
- **Chinese one-line positioning**: 一个基于 OpenClaw 的轻量 3-Agent sidecar，用“首辅—大学士—监审官”的小内阁分工，把 AI 协作变成可审计、可恢复、可干预的交付流程。
- **Differentiation line**: Not more agents. Better separation of responsibility.
- **Chinese differentiation line**: 不是 Agent 越多越强，而是分工越清楚越可交付。

## Current focus

The next practical engineering priorities are:

1. richer maintenance trend and intervention summaries for operators
2. stronger restart / stale / blocked regression coverage
3. broader real OpenClaw integration around upstream gateway / hooks usage
4. production deployment hardening beyond the initial sample scaffolding

## Current scope

This initial migration carries over the reusable task-kernel foundation from the prototype implementation and establishes the independent repository skeleton.

Planned next layers:

- deeper maintenance trend and operator guidance
- broader OpenClaw gateway / webhook integration around the adapter layer
- stronger role health tracking and readiness integration
- production deployment hardening and operational conventions

## Layout

- `sidecar/` — core package
- `sidecar/roles/` — shared and role-specific prompt files
- `docs/` — architecture and migration notes
- `deploy/` — sample deployment assets for Linux systemd and Windows startup

Useful docs for handoff and operations:

- `docs/architecture.md`
- `docs/product-requirements-roadmap.md`
- `docs/operations-runbook.md`

Quick integration smoke command:

- `openclaw-sidecar-smoke`
- or `python -m sidecar.smoke_demo`

This boots a temporary sidecar plus a fake upstream runtime, runs a real HTTP `invoke -> result callback` closed loop, and prints a JSON summary with final task state, endpoint health, and integration readiness.

Remote integration validation command:

- `openclaw-sidecar-remote-validate`
- or `python -m sidecar.remote_validate`

This command uses the current `OPENCLAW_*` environment to validate real upstream wiring. By default it runs **probe-only** checks and reports blocking issues such as missing callback configuration, unreachable upstream endpoints, or incomplete hook registration. Add `--dispatch-sample` when you want it to create one sample task and attempt a real runtime submission.

The JSON output keeps the original flat `blocking_issues` list for compatibility,
and also adds `blocking_issue_groups` so operators can read blockers by layer:

- `config_blockers`
- `probe_blockers`
- `dispatch_blockers`
- `result_blockers`

If `.env` exists, the command will also preload `OPENCLAW_*` defaults from that file unless the same variables are already exported in the shell.

## Environment

See `.env.example` and `.env` for the initial placeholder configuration.

Current gateway / hook related config includes:

- `OPENCLAW_GATEWAY_BASE_URL`
- `OPENCLAW_HOOKS_TOKEN`
- `OPENCLAW_PUBLIC_BASE_URL`
- `OPENCLAW_HOOK_REGISTRATION_RETRY_SEC`
- `OPENCLAW_HOOK_REGISTRATION_FAILURE_ALERT_AFTER`
- `OPENCLAW_RUNTIME_INVOKE_URL`
- `OPENCLAW_RUNTIME_CLI_TIMEOUT_SEC`
- `OPENCLAW_RUNTIME_SUBMIT_RETRY_DELAY_SEC`
- `OPENCLAW_RUNTIME_SUBMIT_MAX_ATTEMPTS`
- `OPENCLAW_INTEGRATION_PROBE_TTL_SEC`

For a **real HTTP invoke -> result callback** loop, treat these three values as a set:

- `OPENCLAW_RUNTIME_INVOKE_URL`
- `OPENCLAW_HOOKS_TOKEN`
- `OPENCLAW_PUBLIC_BASE_URL`

`OPENCLAW_RUNTIME_INVOKE_URL` now supports two integration styles:

- direct HTTP invoke endpoint, for example `http://127.0.0.1:8080/runtime/invoke`
- OpenClaw CLI agent bridge, for example `openclaw-cli://main`

When the CLI bridge style is used, `OPENCLAW_RUNTIME_CLI_TIMEOUT_SEC` controls
how long the sidecar waits for `openclaw agent --agent <agent_id> --json`
before classifying the submission as a timeout. This timeout is independent from
the HTTP runtime bridge timeout so CLI governance can be tuned without changing
HTTP invoke behavior.

Retryable runtime submission failures are also governed by two lightweight
controls:

- `OPENCLAW_RUNTIME_SUBMIT_RETRY_DELAY_SEC` — minimum wait before recovery
  releases a retryable `submit_failed` task back to `idle`
- `OPENCLAW_RUNTIME_SUBMIT_MAX_ATTEMPTS` — maximum total dispatch attempts
  before recovery blocks the task for manual investigation instead of retrying forever

When `openclaw-cli://<agent_id>` is used, the sidecar invokes `openclaw agent --agent <agent_id> --json`, asks the agent to return one strict JSON object for the current sidecar role, and then posts the structured result back into the existing result callback contract.

Only configuring `OPENCLAW_RUNTIME_INVOKE_URL` means the sidecar can submit work outward, but it still cannot advertise a stable authenticated result callback URL back to the upstream runtime. In that state, ops payloads report the integration as `partially_configured` rather than `fully_configured`.

The adapter layer also now includes a lightweight OpenClaw gateway client skeleton for:

- posting ingress/result hooks with the configured token
- registering hook endpoints with an upstream gateway
- querying current hook status from the upstream gateway

The sidecar now exposes an authenticated ingress hook for upstream integration:

- `POST /hooks/openclaw/ingress`
- `POST /hooks/openclaw/result`
- header: `X-OpenClaw-Hooks-Token: <OPENCLAW_HOOKS_TOKEN>`

When direct runtime invoke is enabled, the sidecar will also attach a `callbacks.result` contract to each outgoing invoke payload whenever both `OPENCLAW_PUBLIC_BASE_URL` and `OPENCLAW_HOOKS_TOKEN` are configured. This lets the upstream runtime post the structured role result directly back into `POST /hooks/openclaw/result`.

When `OPENCLAW_PUBLIC_BASE_URL` is configured, the service runner will also try to
auto-register these hook callback URLs with the upstream gateway during startup,
and the current registration state is surfaced under `integration.gateway.hook_registration`.
Failed registration attempts are retried during maintenance cycles, but they are
rate-limited by `OPENCLAW_HOOK_REGISTRATION_RETRY_SEC` so the sidecar does not keep
hammering an unhealthy upstream gateway.

Task event audit summaries now also record whether ingress/result arrived via `local`, `runtime`, or `hook` channels.

The ops and health payloads now also summarize integration configuration state for gateway hooks and runtime invoke wiring.

They also include a lightweight integration probe summary so operators can distinguish between **configured**, **reachable**, **degraded**, and **not configured** states without reading raw logs first.

The probe summary is cached inside the service runner and exposes a `probed_at` timestamp; normal reads reuse the cached result, maintenance cycles refresh it in the background, and `OPENCLAW_INTEGRATION_PROBE_TTL_SEC` controls when a cached probe result should be considered stale and re-checked on demand.

The hook registration summary also exposes `attempt_count`, `last_attempt_at`, and
`next_retry_at` so operators can tell whether automatic repair has already been tried
and when the next retry window opens.

If hook registration keeps failing and the attempt count reaches
`OPENCLAW_HOOK_REGISTRATION_FAILURE_ALERT_AFTER`, the service health payload will
degrade even when task dispatch itself is otherwise idle, so repeated upstream
integration failures are not silently ignored.

If the same repeated upstream failure also crosses the readiness threshold, `readyz`
will return `blocked` with reason `integration=gateway_hook_registration`, making it
clear that the sidecar should not be treated as fully ready for integrated traffic.

When a probe is not cleanly reachable, the component payload may also include structured
`kind` and `message` fields such as `network_error`, `http_4xx`, `http_5xx`,
`probe_error`, or `probe_exception` to help operators triage the likely failure mode quickly.
