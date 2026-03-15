# Upstream Candidate Supply / Provisioning Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the dual-track upstream candidate supply subproject by closing a short discovery window, then producing a provisioning package if no rollout-grade `coordinator` / `executor` candidate is confirmed.

**Architecture:** Treat this as a conditional documentation-and-evidence workflow, not a product-code feature. Chunk 1 closes Gate 1 with a time-boxed discovery report and binary outcome. Chunk 2 executes only as needed: if Gate 1 does not yield enough rollout-grade coverage, create the Gate 2 provisioning package and sync the roadmap docs to the new source of truth.

**Tech Stack:** Markdown docs, PowerShell/SSH, existing AWS staging host, OpenClaw CLI/runtime evidence, sidecar `/healthz` `/readyz` `/ops/summary`, git

**Execution Context:** Execute this plan from the existing worktree at `D:\code\openclaw-3agent-sidecar\.worktrees\phase0-agent-inventory` so the new docs and Phase 0 references stay on the same branch context.

---

## File Structure

- Create: `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md` — Gate 1 execution artifact; records the short discovery scope, evidence sources used, any newly discovered candidates, and the binary gate result (`found candidate` or `no additional candidate`)
- Create: `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md` — Gate 2 output package; contains the candidate supply spec, naming / mapping draft, and validation entry contract for missing upstream roles
- Modify: `docs/plans/2026-03-15-real-3-agent-target-plan.md` — add a concise status update that points to the new discovery gate result and, if needed, the provisioning package
- Reference only: `docs/superpowers/specs/2026-03-15-upstream-candidate-supply-provisioning-design.md`
- Reference only: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`
- Reference only: `deploy/aws-role-specific-agent-staging-rollout-checklist.md`

---

## Prerequisites

- Confirm execution is happening from `D:\code\openclaw-3agent-sidecar\.worktrees\phase0-agent-inventory`
- Confirm a valid SSH key for `ubuntu@13.51.172.206` is available
- Preferred local key path: `C:/git_ssh/openclaw-key-2.pem`
- If the preferred key path is not present, stop and replace the command examples in this plan with the actual valid local key path before running Gate 1; do not keep the stale example path in live commands
- Confirm the staging host and sidecar service are expected to be reachable before starting the discovery window

Recommended pre-flight commands before Task 1:

```powershell
Test-Path C:/git_ssh/openclaw-key-2.pem
ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "echo preflight-ok"
ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "curl -s http://127.0.0.1:9600/readyz"
```

Expected:

- key check returns `True`
- SSH prints `preflight-ok`
- `readyz` returns a valid JSON payload rather than timing out or refusing connection

---

## Chunk 1: Close Gate 1 with a short discovery report

### Task 1: Create the Gate 1 report skeleton and freeze the entry baseline

**Files:**

- Create: `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`
- Reference: `docs/superpowers/specs/2026-03-15-upstream-candidate-supply-provisioning-design.md`
- Reference: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`

- [ ] **Step 1: Create the report file with fixed section headings**

Create the file with these sections:

```markdown
# Upstream Candidate Discovery Gate Report

## Scope
## Entry Baseline
## Discovery Window
## Evidence Sources Used
## Discovery Findings
## Candidate Qualification Notes
## Gate Result
## Next Action
## Escalation / Inconclusive State
```

Expected result: the report exists and is clearly scoped to Gate 1 only.

- [ ] **Step 2: Copy only the already-proven entry baseline facts**

Populate `## Entry Baseline` with facts already validated by Phase 0:

- `reviewer -> sysarch`
- `coordinator -> main` (fallback)
- `executor -> main` (fallback)
- confirmed host-visible agents: `main`, `sysarch`
- current blocker: `upstream agent supply gap`
- current honest label: reviewer-only role-specific routing, not real 3-agent

Expected result: Gate 1 starts from the known truth instead of re-litigating Phase 0.

- [ ] **Step 3: Define the explicit discovery window in the report**

Under `## Discovery Window`, write:

- start date: `2026-03-15`
- execution start timestamp: record the actual local date-time when Gate 1 evidence collection begins
- maximum duration: `<= 1 working day`
- allowed result forms:
  - `found candidate`
  - `no additional candidate`
- explicit non-goals:
  - no live role mapping change
  - no new experimental deployment
  - no promotion of `main` to dedicated candidate

Expected result: the report itself enforces the Gate 1 time-box and rules.

- [ ] **Step 4: Commit the discovery report skeleton**

Run:

```bash
git add docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md
git commit -m "docs: add upstream discovery gate report"
```

Expected: one new committed report with no TODO markers.

### Task 2: Collect the minimum final discovery evidence

**Files:**

- Modify: `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`

- [ ] **Step 1: Re-check sidecar routing evidence to confirm the live baseline has not changed**

Reuse the exact field names already observed in `docs/plans/2026-03-15-phase0-agent-inventory-report.md` as the primary baseline. If the live payload shape differs, record the actual keys returned instead of forcing stale field names.

Before attempting SSH, verify the key file exists locally:

```powershell
Test-Path C:/git_ssh/openclaw-key-2.pem
```

Expected: `True`

Run:

```powershell
ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "curl -s http://127.0.0.1:9600/ops/summary"
```

Record at minimum:

- `integration.runtime_invoke.bridge.role_agent_mapping.configured_agents`
- `integration.runtime_invoke.bridge.role_agent_mapping.fallback_agent_id`
- `integration.runtime_invoke.bridge.role_agent_mapping.routing_mode`

Expected: still reviewer-only role-specific routing with `main` fallback.

If SSH access fails, the host is unreachable, or `ops/summary` is unavailable, stop Gate 1 execution and escalate before proceeding past Task 2; do not invent substitute conclusions from stale Phase 0 evidence.

For this plan, escalate by recording the failure in the Gate 1 report draft and notifying the sidecar owner / human requester that Gate 1 is blocked on AWS access or service availability.

In that case, mark Gate 1 as `inconclusive`, stop the plan without entering Gate 2, and wait for restored AWS access before resuming.

- [ ] **Step 2: Re-check host-visible agents and latest session traces**

Run:

```powershell
ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "printf '%s\n' '---AGENTS---'; find /home/ubuntu/.openclaw/agents -maxdepth 1 -mindepth 1 -type d | sed -n '1,80p'; printf '%s\n' '---LATEST_MAIN---'; ls -lt --time-style=full-iso /home/ubuntu/.openclaw/agents/main/sessions 2>/dev/null | sed -n '1,5p'; printf '%s\n' '---LATEST_SYSARCH---'; ls -lt --time-style=full-iso /home/ubuntu/.openclaw/agents/sysarch/sessions 2>/dev/null | sed -n '1,5p'"
```

Expected:

- visible agents still include `main` and `sysarch`
- same-day or recent session evidence is visible for active agents
- any new agent directory names are explicitly captured if present

- [ ] **Step 3: Do one last naming-oriented discovery pass across current docs**

Use workspace regex search over `docs/**` and `deploy/**` for possible candidate naming clues. If using the editor search UI, enable regex mode. If using terminal search, use a regex-capable command such as `rg -n -e "coord-|planner-|exec-|worker-|review-|agent.?id" docs deploy`.

Search for:

```text
coord-|planner-|exec-|worker-|review-|agent.?id
```

Expected:

- either no new real candidate names appear
- or a short list of name clues that must be explicitly compared against host evidence

- [ ] **Step 4: Record the evidence sources used and what each source contributed**

Update `## Evidence Sources Used` and `## Discovery Findings` with:

- exact command/search performed
- either the raw excerpt or the exact extracted key lines that justify the conclusion
- what it confirmed
- whether it added a real new candidate, only a naming clue, or nothing new

Use this recording shape for each evidence item:

```markdown
- source: <command or search>
- excerpt:
  - <exact field or returned line>
- contribution: <what this proved>
- disposition: <new candidate | naming clue only | no new information>
```

Expected result: the report shows why Gate 1 stopped where it stopped.

### Task 3: Produce the Gate 1 result and branch decision

**Files:**

- Modify: `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`
- Reference: `docs/superpowers/specs/2026-03-15-upstream-candidate-supply-provisioning-design.md`

- [ ] **Step 1: Write candidate qualification notes for every newly surfaced name**

Under `## Candidate Qualification Notes`, classify each surfaced item as one of:

- not a real candidate
- naming clue only
- `discovery candidate`
- `rollout-grade candidate`

Use the qualification rules from `docs/superpowers/specs/2026-03-15-upstream-candidate-supply-provisioning-design.md` exactly:

- `discovery candidate` requires real existence evidence, no conflict with known invalid candidates, and a plausible role-direction link
- `rollout-grade candidate` requires explicit role-direction fit, callable or equivalent run evidence, current activity or maintainability evidence, and no obvious sidecar contract-breakage risk

For each item, state why in one bullet using evidence, not guesswork.

Expected: every surfaced name has a disposition.

- [ ] **Step 2: Write the binary Gate 1 result in fixed format**

Use one of these exact result shapes:

```text
gate_result -> found candidate
candidate -> <agent_id>
qualification -> discovery candidate | rollout-grade candidate
next_action -> candidate validation / rollout planning
```

or

```text
gate_result -> no additional candidate
candidate -> none
next_action -> Gate 2 provisioning
blocker -> upstream agent supply gap
```

or

```text
gate_result -> inconclusive
candidate -> unknown
reason -> AWS access or service availability blocked Gate 1 evidence collection
next_action -> wait for restored access before resuming Gate 1
```

Expected: Gate 1 ends with a fixed result shape, not a vague “more investigation later”.

- [ ] **Step 3: Apply the branch rule explicitly**

Use exactly one of the following two branch outcomes under `## Next Action`.

If Gate 1 yields no newly discovered `rollout-grade candidate` in either the `coordinator` or `executor` direction, add this sentence.

For this plan, “materially shrinks the supply gap” means at least one newly discovered `rollout-grade candidate` exists in either the `coordinator` or `executor` direction. If all surfaced items remain only naming clues or `discovery candidate`, the supply gap remains active.

Then write:

```text
Gate 2 is required because Gate 1 did not produce enough rollout-grade coverage for coordinator / executor supply.
```

If Gate 1 did produce enough rollout-grade coverage, write exactly:

```text
Gate 2 is deferred because Gate 1 produced a rollout-grade candidate that is ready for candidate validation / rollout planning.
```

Expected: the handoff into or away from Gate 2 is explicit.

- [ ] **Step 4: Commit the Gate 1 result**

Run:

```bash
git add docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md
git commit -m "docs: conclude upstream discovery gate"
```

Expected: the Gate 1 report becomes the single source of truth for the discovery closure.

- [ ] **Step 5: If Gate 2 is deferred, sync the roadmap immediately**

If Task 3 concluded with Gate 2 deferred, update `docs/plans/2026-03-15-real-3-agent-target-plan.md` right away with:

- a pointer to `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`
- a one-line summary that Gate 1 found a candidate and Gate 2 was deferred
- the reminder that real 3-agent language still remains blocked until full role coverage is evidenced

Then run:

```bash
git add docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md docs/plans/2026-03-15-real-3-agent-target-plan.md
git commit -m "docs: sync discovery gate outcome"
```

Expected: the roadmap is updated even when Gate 2 is not needed.

---

## Chunk 2: If needed, produce the Gate 2 provisioning package

Execute Tasks 4–6 only if Gate 1 concluded with `next_action -> Gate 2 provisioning`.

### Task 4: Create the provisioning package skeleton

**Files:**

- Create: `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md`
- Reference: `docs/superpowers/specs/2026-03-15-upstream-candidate-supply-provisioning-design.md`
- Reference: `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`

- [ ] **Step 1: Create the provisioning package only if Gate 1 resolved to Gate 2**

If the Gate 1 report says `next_action -> Gate 2 provisioning`, create the file with these sections:

```markdown
# Upstream Candidate Provisioning Package

## Scope
## Discovery Closure Input
## Candidate Supply Spec
## Naming and Mapping Draft
## Validation Entry Contract
## Recommended Upstream Ask
## Notes for Follow-on Rollout Planning
```

If Gate 1 deferred Gate 2, skip this task and note in the roadmap sync update from Task 6, Step 3 that the file was intentionally not created.

Expected: no unnecessary Gate 2 artifact when discovery already solved the next step.

- [ ] **Step 2: Copy the discovery closure input exactly**

Under `## Discovery Closure Input`, paste the Gate 1 conclusion lines:

- `gate_result -> ...`
- `candidate -> ...`
- `next_action -> ...`
- `blocker -> upstream agent supply gap` (if present)

Expected: the provisioning package clearly states why it exists.

### Task 5: Write the candidate supply spec and naming draft

**Files:**

- Modify: `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md`

**Prerequisite:** Task 4 must have created the provisioning package file.

- [ ] **Step 1: Write the candidate supply spec for missing roles**

Under `## Candidate Supply Spec`, define at minimum:

- missing role directions:
  - `coordinator-grade`
  - `executor-grade`
- what each role should be good at
- what each role should explicitly not be used for
- why `reviewer` supply is not the current missing leg

Ground these role boundaries in the existing canonical role materials before writing them:

- `AGENTS.md`
- `sidecar/roles/shared/AGENTS.md`
- `sidecar/roles/coordinator/SOUL.md`
- `sidecar/roles/executor/SOUL.md`
- `sidecar/roles/reviewer/SOUL.md`

Expected: the supply gap is translated from “missing names” into “missing responsibilities”.

- [ ] **Step 2: Write the naming and mapping draft**

Under `## Naming and Mapping Draft`, include:

- suggested `coordinator` naming family: `coord-*` / `planner-*`
- suggested `executor` naming family: `exec-*` / `worker-*`
- current reviewer baseline: `sysarch`
- `main` retained as fallback / rollback / compatibility only
- a note that naming mismatch alone does not disqualify a real candidate

Make it explicit that these naming families are soft recommendations for consistency, not hard disqualifiers for otherwise valid upstream candidates.

Expected: future mapping discussions have a concrete naming baseline without turning naming into the only signal.

- [ ] **Step 3: Write the recommended upstream ask in direct operator language**

Under `## Recommended Upstream Ask`, write a concise request template that names:

- the missing candidate types
- the desired responsibility boundaries
- the need for a verifiable callable agent id
- the need for evidence sufficient to enter rollout planning

Expected: a human can forward this section upstream without rewriting it from scratch.

### Task 6: Write the validation entry contract and planning handoff

**Files:**

- Modify: `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md`
- Modify: `docs/plans/2026-03-15-real-3-agent-target-plan.md`

- [ ] **Step 1: Write the validation entry contract as an actionable checklist**

Under `## Validation Entry Contract`, include checkbox bullets for:

- strong existence evidence
- callable evidence
- role orientation evidence
- no obvious sidecar contract breakage risk
- validation evidence requirements that the next rollout planning document must check before a human records a `rollout-grade` decision

Define that the final `rollout-grade` decision is recorded by the sidecar owner or phase lead in the next rollout planning document after this checklist evidence is assembled; this plan does not require inventing a new approval body.

Expected: later rollout planning can use this section as its intake gate.

- [ ] **Step 2: Add follow-on rollout planning notes**

Under `## Notes for Follow-on Rollout Planning`, write:

- if a future `coordinator-grade` candidate appears, it feeds Phase 2 planning first
- if a future `executor-grade` candidate appears without coordinator coverage, the supply gap is only partially reduced
- real 3-agent language remains blocked until three independent upstream roles are truly evidenced

Expected: the next planner does not over-claim success from partial supply.

- [ ] **Step 3: Update the real 3-agent target plan with a concise execution status note**

Add a short section or paragraph that points to:

- `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`
- `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md` (only if created)

Summarize one of two states:

- Gate 1 found a candidate and Gate 2 was deferred
- Gate 1 did not find enough coverage and Gate 2 provisioning package is now the active source of truth

If Gate 2 was deferred, use this roadmap update as the execution log location for that deferral; do not create a separate placeholder file just to say Gate 2 was skipped.

Expected: the roadmap doc stays current without restating the full package contents.

- [ ] **Step 4: Commit the Gate 2 package and roadmap sync**

Run:

```bash
git add docs/plans/2026-03-15-upstream-candidate-provisioning-package.md docs/plans/2026-03-15-real-3-agent-target-plan.md
git commit -m "docs: add upstream provisioning package"
```

If Gate 2 was deferred and only the roadmap doc changed, add and commit only that file with a more accurate message such as:

```bash
git add docs/plans/2026-03-15-real-3-agent-target-plan.md
git commit -m "docs: sync discovery gate outcome"
```

---

## Chunk 3: Verify the package and prepare execution handoff

### Task 7: Validate the modified docs and record package status

**Files:**

- Verify: `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`
- Verify: `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md` (if created)
- Verify: `docs/plans/2026-03-15-real-3-agent-target-plan.md`

- [ ] **Step 1: Run Markdown/editor diagnostics on every modified doc**

Use the editor diagnostics / problems check for all changed Markdown files.

Expected: no blocking markdown issues.

- [ ] **Step 2: Re-read the docs together for claim discipline**

Verify they all agree on:

- current honest system label
- whether Gate 1 found anything real
- whether Gate 2 is active or deferred
- whether `upstream agent supply gap` still exists

Expected: no accidental claim that real 3-agent has started.

- [ ] **Step 3: Validate the Gate 1 result shape before finalizing**

Before the final verification commit, confirm the discovery gate report includes exactly one of these `gate_result` shapes:

- `gate_result -> found candidate`
- `gate_result -> no additional candidate`
- `gate_result -> inconclusive`

Also confirm the companion lines for `candidate -> ...` and `next_action -> ...` exist and match the chosen branch.

Expected: downstream Gate 2 pickup logic can rely on a fixed result format.

- [ ] **Step 4: Review git diff for scope discipline**

Run:

```bash
git diff --stat HEAD~1..HEAD
```

and, before finalizing, inspect current working tree scope.

Expected: only the planned docs changed.

- [ ] **Step 5: Record verification evidence in the final changed doc**

Append a `## Verification Evidence` section to the final active source-of-truth doc that records:

- which evidence commands were run
- whether diagnostics passed
- whether Gate 2 was activated or deferred
- what the final active source-of-truth documents are

If Gate 2 was deferred, put this section in `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`. If Gate 2 was activated, put it in `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md`.

Expected: the package contains its own audit tail.

- [ ] **Step 6: Final completion commit**

If verification required a final edit, commit it with a message such as:

```bash
git add <changed-files>
git commit -m "docs: verify candidate supply package"
```

If the working tree is already clean because the verification evidence was captured earlier, do not create an empty commit.
