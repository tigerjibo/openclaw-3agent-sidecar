# Architecture

`openclaw-3agent-sidecar` is an orchestration layer built on top of the official OpenClaw runtime.

## Layers

1. Official OpenClaw: gateway, routing, skills, webhook, agent runtime
2. Sidecar kernel: tasks, task_events, state machine, API, projections
3. Sidecar runtime: dispatcher, scheduler, recovery, role health (planned)
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
