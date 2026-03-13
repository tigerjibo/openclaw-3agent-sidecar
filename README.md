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

1. persistent DB path in `sidecar/service_runner.py`
2. periodic recovery / health driving from scheduler / service runner
3. stronger restart / stale / blocked regression coverage
4. real OpenClaw ingress / invoke / result wiring

## Current scope

This initial migration carries over the reusable task-kernel foundation from the prototype implementation and establishes the independent repository skeleton.

Planned next layers:

- persistent DB path in `service_runner.py`
- scheduler / service runner wiring for periodic recovery
- deeper role health tracking and readiness integration
- real OpenClaw ingress / invoke / result integration
- production deployment scaffolding

## Layout

- `sidecar/` — core package
- `sidecar/roles/` — shared and role-specific prompt files
- `docs/` — architecture and migration notes

## Environment

See `.env.example` and `.env` for the initial placeholder configuration.
