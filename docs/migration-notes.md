# Migration Notes

This repository was initialized by migrating the reusable kernel foundation out of the previous prototype workspace.

## Migrated now

- contracts
- storage
- models
- events
- state machine
- runtime mode
- rollout policy helper
- projection/detail/metrics foundation
- local API / HTTP service / service runner foundation
- ingress adapter
- agent invoke adapter
- result adapter
- dispatcher
- scheduler
- recovery
- role health foundation
- service health integration for role-level health snapshots
- minimal role files
- adapter loop tests
- runtime loop tests

## Still pending

- persistent DB path in service runner
- periodic recovery / health scheduling in service runner
- real OpenClaw invoke / result wiring
- production deployment scaffolding
