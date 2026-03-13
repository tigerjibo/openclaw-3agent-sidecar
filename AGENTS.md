# AGENTS.md

## Repository role

This repository is the **primary development home** for the independent `openclaw-3agent-sidecar` project.

Do **not** continue the sidecar main implementation in:

- `M:\code\openclaw`

That older workspace is now only a historical source of migration context and reference documents.

## Project identity

`openclaw-3agent-sidecar` is:

- a sidecar orchestration layer on top of the official `openclaw/openclaw` runtime
- not an OpenClaw fork
- not a project that should modify official OpenClaw core source code

## Core responsibility split

### Official OpenClaw owns

- gateway
- routing
- webhook
- workspace / skills
- session / agent runtime

### This repository owns

- task kernel (`tasks`, `task_events`)
- 3-agent state machine
- adapters (`ingress`, `invoke`, `result`)
- runtime (`dispatcher`, `scheduler`, later `recovery`, `agent_health`)
- projections / detail / metrics / audit trail

## Role model

Three fixed roles:

- `coordinator`
- `executor`
- `reviewer`

For external-facing product communication, these roles may be presented as a **Ming-style small cabinet**:

- `coordinator` → 首辅 / Chief Grand Secretary
- `executor` → 大学士 / Grand Secretary
- `reviewer` → 监审官 / Supervising Reviewer

Do not replace the canonical runtime role ids in code, tests, APIs, or data models.

Role prompt files are in:

- `sidecar/roles/shared/AGENTS.md`
- `sidecar/roles/coordinator/SOUL.md`
- `sidecar/roles/executor/SOUL.md`
- `sidecar/roles/reviewer/SOUL.md`

## Current implementation status

Already implemented:

- task kernel foundation
- minimal adapter loop
- minimal runtime loop
- recovery foundation
- agent health foundation
- service health integration with role health snapshot
- local HTTP service foundation
- tests for adapter/runtime minimal loop

Still pending:

- persistent DB path in `sidecar/service_runner.py`
- periodic recovery / health driving in `sidecar/service_runner.py`
- real integration with official OpenClaw runtime
- production deployment scaffolding

## Required reading order for any new agent

1. `README.md`
2. `docs/project-introduction.md`
3. `docs/product-requirements-roadmap.md`
4. `docs/architecture.md`
5. `docs/migration-notes.md`
6. `docs/adapter-contract.md`
7. current code under `sidecar/`
8. current tests under `tests/`

## Working rules

1. Do not move sidecar implementation back into the old repo.
2. Do not modify official OpenClaw core code unless explicitly re-decided by humans.
3. Treat sidecar as the only task truth source.
4. Prefer TDD for any new behavior.
5. Before claiming completion, run fresh verification.

## Minimum verification commands

Run after meaningful code changes:

- `pytest tests -q`
- `python -m compileall sidecar`

## Recommended next task

The next recommended implementation target is:

- persistent DB support in `sidecar/service_runner.py`

After that:

- periodic recovery / health scheduling
- real OpenClaw integration wiring
