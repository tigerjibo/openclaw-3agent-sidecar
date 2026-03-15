# Upstream Candidate Supply Request

## Suggested issue title

Request upstream `coordinator-grade` and `executor-grade` agent supply for real 3-agent rollout

## Summary

We have completed the Phase 0 inventory round and the follow-on dual-track discovery / provisioning work for `openclaw-3agent-sidecar`.

Current validated AWS staging state remains:

- `reviewer -> sysarch`
- `coordinator -> main` (fallback)
- `executor -> main` (fallback)

Validated blocker remains:

```text
blocker -> upstream agent supply gap
```

Gate 1 re-confirmed that no additional host-verified upstream candidate id is currently available beyond `main` and `sysarch`.

We are therefore requesting upstream supply for the two still-missing dedicated role directions required for real 3-agent rollout.

## What we need

### 1. coordinator-grade candidate

Please provide a callable upstream agent id for a planning-oriented candidate that can:

- clarify task goals
- define acceptance criteria
- identify key risks before execution
- propose structured next execution steps
- produce planning-oriented output without acting as the main executor

This candidate should **not** be positioned as:

- the main implementation worker
- the final reviewer / approver
- a silent alias for fallback `main`

### 2. executor-grade candidate

Please provide a callable upstream agent id for an execution-oriented candidate that can:

- perform the main task work
- return structured result evidence
- report blockers and residual risks honestly
- produce delivery-oriented output without self-approving

This candidate should **not** be positioned as:

- the planner that defines task acceptance
- the reviewer that approves or rejects work
- a silent alias for fallback `main`

## Minimum evidence required for each proposed candidate

For each proposed upstream candidate, please include enough evidence for rollout intake:

- existence proof
  - example: authoritative registration, host-visible presence, or equivalent maintenance record
- callable proof
  - example: successful invoke or equivalent runtime execution proof
- role-fit explanation
  - short explanation of why the candidate is better aligned to `coordinator` or `executor`
- known constraints or risks
  - anything likely to affect sidecar callback / result contract compatibility

## Naming guidance

Suggested naming families for consistency are:

- `coordinator` → `coord-*` / `planner-*`
- `executor` → `exec-*` / `worker-*`
- `reviewer` → current stable reviewer baseline or future `review-*`

These are recommendations, not hard blockers. A differently named candidate is still acceptable if its evidence and role fit are strong.

## Why this matters

We already have:

- 3 fixed runtime roles in sidecar
- reviewer-only role-specific routing validated in AWS staging
- closed-loop result callback baseline

What we do **not** yet have is real 3-agent coverage, because `coordinator` and `executor` still fall back to `main`.

Until dedicated upstream candidates exist and pass intake validation, the system should continue to be described honestly as:

- 3-role sidecar workflow
- reviewer-only role-specific routing
- not yet full real 3-agent

## References

- Phase 0 report: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`
- Gate 1 closure: `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`
- Gate 2 provisioning package: `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md`

## Requested next response

Please reply with one of the following:

1. one proposed `coordinator-grade` agent id plus evidence
2. one proposed `executor-grade` agent id plus evidence
3. both candidates plus evidence
4. a clear statement that new upstream supply is not yet available, so rollout remains blocked
