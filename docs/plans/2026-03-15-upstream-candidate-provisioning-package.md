# Upstream Candidate Provisioning Package

## Scope

This package is the Gate 2 output for the upstream candidate supply / provisioning subproject.

It exists because Gate 1 ended with:

- `gate_result -> no additional candidate`
- `candidate -> none`
- `next_action -> Gate 2 provisioning`
- `blocker -> upstream agent supply gap`

This package does not change live AWS role mapping. Its purpose is to define what upstream supply is missing, how missing roles should be described, and what minimum evidence a future candidate must provide before entering rollout planning.

## Discovery Closure Input

- `gate_result -> no additional candidate`
- `candidate -> none`
- `next_action -> Gate 2 provisioning`
- `blocker -> upstream agent supply gap`

Gate 1 re-confirmed that:

- live reviewer-only role-specific routing is still active
- host-visible agents remain `main` and `sysarch`
- no new host-verified upstream candidate id was discovered
- naming patterns in docs did not upgrade into real callable candidates

## Candidate Supply Spec

### Missing role directions

The currently missing upstream supply directions are:

- `coordinator-grade`
- `executor-grade`

`reviewer` is not the currently missing leg because `sysarch` remains the validated reviewer-oriented baseline.

### coordinator-grade candidate requirements

A `coordinator-grade` candidate should be good at:

- clarifying task goals
- defining acceptance criteria
- identifying risks before execution
- proposing structured next execution steps
- producing stable planning-oriented output without pretending the work is already done

A `coordinator-grade` candidate should **not** be used as:

- the main implementation worker
- the final approval authority
- a substitute for `executor` evidence production
- a substitute for `reviewer` rejection / approval decisions

This role boundary is grounded in the canonical role materials:

- `sidecar/roles/shared/AGENTS.md`
- `sidecar/roles/coordinator/SOUL.md`

### executor-grade candidate requirements

An `executor-grade` candidate should be good at:

- performing the main assigned work
- reporting result summary and concrete evidence
- surfacing blockers and residual risks honestly
- producing structured delivery-oriented output rather than redefining the task

An `executor-grade` candidate should **not** be used as:

- the planner who defines the goal and acceptance contract
- the reviewer who independently approves the work
- a silent worker that hides failures or open issues

This role boundary is grounded in the canonical role materials:

- `sidecar/roles/shared/AGENTS.md`
- `sidecar/roles/executor/SOUL.md`

### reviewer supply note

`reviewer` supply is not the active missing leg in this Gate 2 package because:

- `sysarch` already serves as the reviewer-oriented validated baseline
- the present blocker is not “missing any reviewer path”
- the present blocker is the lack of dedicated `coordinator-grade` and `executor-grade` upstream candidates

At the same time, `sysarch` should not be repurposed as the default answer for missing `coordinator` or `executor` supply without a separate, evidence-backed validation decision.

## Naming and Mapping Draft

### Suggested naming families

Suggested naming families for future upstream candidates are:

- `coordinator` → `coord-*` / `planner-*`
- `executor` → `exec-*` / `worker-*`
- `reviewer` → current stable reviewer baseline or future `review-*` family

These are soft recommendations for consistency, not hard disqualifiers. A future candidate with a different naming pattern may still be valid if its role behavior and evidence are strong enough.

### Current mapping baseline

The current honest baseline remains:

- `reviewer -> sysarch`
- `coordinator -> main` (fallback)
- `executor -> main` (fallback)

### Fallback rule

`main` remains:

- fallback
- rollback target
- compatibility path

`main` is **not** the steady-state naming answer for dedicated `coordinator` or `executor` supply.

### Mapping intent draft

Once valid new candidates exist, the intended mapping direction should become:

- `coordinator -> <coordinator-grade-agent-id>`
- `executor -> <executor-grade-agent-id>`
- `reviewer -> sysarch` or a separately validated reviewer-grade successor
- `main` retained only for fallback / rollback

## Validation Entry Contract

A future upstream candidate must satisfy all of the following evidence requirements before the next rollout planning document can record it as `rollout-grade`.

- [ ] strong existence evidence
  - example: host-visible agent directory, authoritative upstream registration, or equivalent maintenance record
- [ ] callable evidence
  - example: successful invoke or equivalent runtime proof that the candidate can actually run
- [ ] role orientation evidence
  - example: outputs or prior usage that clearly align with `coordinator` or `executor` responsibilities
- [ ] no obvious sidecar contract-breakage risk
  - example: no immediate sign that structured callback / result expectations would be broken
- [ ] explicit human rollout-grade decision recorded later
  - the sidecar owner or phase lead records this decision in the next rollout planning document after the above evidence is assembled

This package defines the intake gate; it does not invent a new approval body or prematurely declare any missing role as solved.

## Recommended Upstream Ask

Use the following operator-facing request when coordinating upstream supply:

> We currently have a validated reviewer-oriented upstream agent (`sysarch`) but still lack dedicated `coordinator-grade` and `executor-grade` candidates for real 3-agent rollout. Please provide callable upstream agent ids for:
>
> 1. a planning-oriented candidate that can clarify goals, define acceptance criteria, identify risks, and propose next steps without acting as the main executor;
> 2. an execution-oriented candidate that can perform the main task, return structured result evidence, and report blockers without self-approving.
>
> For each proposed candidate, please include enough evidence for rollout intake: existence proof, callable proof, and a short explanation of why the candidate fits the intended role direction.

## Notes for Follow-on Rollout Planning

- If a future `coordinator-grade` candidate appears first, it should feed Phase 2 planning before any claim of broader 3-agent readiness.
- If a future `executor-grade` candidate appears without coordinator coverage, the supply gap is only partially reduced.
- If future candidates appear for both missing directions, each still needs intake validation before they are treated as rollout-grade.
- Real 3-agent wording remains blocked until three independent upstream role targets are actually evidenced.
