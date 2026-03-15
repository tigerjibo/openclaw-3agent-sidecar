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

- real OpenClaw invoke / result wiring
- broader staged role-specific rollout beyond reviewer-only validation
- production deployment automation / scaffolding hardening
- roadmap and handoff document synchronization with current verified state
