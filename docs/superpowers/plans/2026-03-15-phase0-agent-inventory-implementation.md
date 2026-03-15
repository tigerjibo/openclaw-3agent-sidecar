# Phase 0 Agent Inventory Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete Phase 0 for real 3-agent rollout by collecting upstream agent evidence from AWS staging, classifying candidates by role, and producing a documented go / no-go decision for Phase 2.

**Architecture:** Treat this as an evidence-and-decision workflow, not a code feature. The work is split into two focused outputs: (1) a factual inventory report with raw evidence and candidate classification, and (2) a concise decision update that feeds the existing rollout docs without changing production role mapping.

**Tech Stack:** Markdown docs, PowerShell/SSH, existing AWS staging host, OpenClaw CLI evidence, sidecar `/healthz` `/readyz` `/ops/summary`, git

---

## File Structure

- Create: `docs/plans/2026-03-15-phase0-agent-inventory-report.md` — primary execution artifact for raw evidence, candidate table, confidence ratings, and final go / no-go decision
- Modify: `docs/plans/2026-03-15-phase0-agent-inventory-plan.md` — add a short “execution status / findings” section once the report exists
- Modify: `docs/plans/2026-03-15-real-3-agent-target-plan.md` — update current blocker wording only if Phase 0 changes the known candidate picture
- Reference only: `docs/superpowers/specs/2026-03-15-phase0-agent-inventory-design.md`
- Reference only: `docs/plans/2026-03-15-role-specific-agent-staging-validation.md`
- Reference only: `deploy/aws-role-specific-agent-staging-rollout-checklist.md`

---

## Chunk 1: Build the inventory report and collect hard evidence

### Task 1: Create the Phase 0 report skeleton

**Files:**

- Create: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`
- Reference: `docs/superpowers/specs/2026-03-15-phase0-agent-inventory-design.md`

- [ ] **Step 1: Create the report file with fixed section headings**

Create a Markdown report with these sections:

```markdown
# Phase 0 Agent Inventory Report

## Scope
## Current staging baseline
## Evidence collection log
## Candidate inventory table
## Role classification notes
## Confidence ratings
## Go / No-Go decision
## Recommended next action
```

- [ ] **Step 2: Pre-fill the known baseline facts from existing validated docs**

Copy only already-proven facts into `## Current staging baseline`:

- `reviewer -> sysarch`
- `coordinator -> main`
- `executor -> main`
- known visible agents: `main`, `sysarch`
- known invalid historical candidate: `work`

Expected result: the report starts with current truth, not blank placeholders.

- [ ] **Step 3: Commit the report skeleton**

Run:

```bash
git add docs/plans/2026-03-15-phase0-agent-inventory-report.md
git commit -m "docs: add phase0 inventory report skeleton"
```

Expected: one new Markdown file committed with no TODO markers.

### Task 2: Collect AWS staging evidence

**Files:**

- Modify: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`

- [ ] **Step 1: Capture current sidecar baseline health evidence**

Run from the workspace terminal:

```powershell
ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "curl -s http://127.0.0.1:9600/healthz; printf '\n---READYZ---\n'; curl -s http://127.0.0.1:9600/readyz; printf '\n---OPS---\n'; curl -s http://127.0.0.1:9600/ops/summary"
```

Expected:

- `healthz.status=ok`
- `readyz.status=ready`
- `ops.summary.integration.runtime_invoke.bridge.role_agent_mapping` visible

- [ ] **Step 2: Paste the exact observed facts into `## Evidence collection log`**

Record:

- timestamp of the command
- health result
- readiness result
- current configured role mapping
- fallback agent id

Expected result: the report contains reproducible evidence, not paraphrase-only notes.

- [ ] **Step 3: Capture visible agent inventory from the host**

Run:

```powershell
ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "printf '%s\n' '---AGENT_DIRS---'; ls -1 /home/ubuntu/.openclaw/agents 2>/dev/null | sed -n '1,120p'; printf '%s\n' '---RECENT_AGENT_SESSIONS---'; find /home/ubuntu/.openclaw/agents -maxdepth 3 -type f -name '*.jsonl' | sed -n '1,80p'"
```

Expected:

- at least `main` and `sysarch` appear
- recent session evidence appears for active agents

- [ ] **Step 4: Attempt CLI-side inventory discovery if supported**

Run:

```powershell
ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "openclaw agent list 2>&1 | sed -n '1,120p'"
```

Expected:

- either a usable list, or a clear unsupported / empty output captured as evidence

- [ ] **Step 5: Record the result honestly**

Update the report with:

- whether CLI listing worked
- whether it added any new candidates
- whether the evidence remains limited to directory/session discovery

- [ ] **Step 6: Commit the evidence update**

Run:

```bash
git add docs/plans/2026-03-15-phase0-agent-inventory-report.md
git commit -m "docs: capture phase0 agent evidence"
```

Expected: report now contains factual AWS evidence and raw candidate discovery inputs.

### Task 3: Build the candidate inventory table

**Files:**

- Modify: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`

- [ ] **Step 1: Create the candidate table with explicit columns**

Use this shape:

```markdown
| agent_id | source_of_truth | recent_session_seen | invokeable | suggested_role | confidence | notes |
| --- | --- | --- | --- | --- | --- | --- |
```

- [ ] **Step 2: Add rows for confirmed current agents**

Populate rows for:

- `main`
- `sysarch`

Populate from evidence only.

- [ ] **Step 3: Add rows for any newly discovered candidate agents**

If no new agents are discovered, explicitly write that no new candidate rows were added.

- [ ] **Step 4: Run a self-check against the spec**

Verify the table answers:

- what exists
- what has evidence
- what can be called
- what role it seems suited for

Expected: no blank semantic fields except where the evidence is genuinely unavailable and explicitly called out.

---

## Chunk 2: Classify candidates, decide Go/No-Go, and update shared docs

### Task 4: Classify candidates by role tendency and confidence

**Files:**

- Modify: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`
- Reference: `docs/superpowers/specs/2026-03-15-phase0-agent-inventory-design.md`

- [ ] **Step 1: Write role classification notes for each candidate**

For each candidate row, add short evidence-backed notes explaining whether it is:

- `coordinator-oriented`
- `executor-oriented`
- `reviewer-oriented`
- `fallback only`

Use a consistent bullet format under `## Role classification notes`, for example:

```markdown
- `sysarch`: reviewer-oriented — recent reviewer session evidence exists; prior reviewer-only staging validation already succeeded.
- `main`: fallback only — current fallback agent; no evidence yet that it should be treated as a dedicated coordinator/executor candidate.
```

- [ ] **Step 2: Apply confidence rules exactly as specified**

Assign only one of:

- `high`
- `medium`
- `low`

Use the spec thresholds rather than intuition.

- [ ] **Step 3: Make the reviewer baseline explicit**

Record that:

- `sysarch` is `reviewer-oriented`
- confidence is `high`
- basis is prior real reviewer-only staging validation

- [ ] **Step 4: Make the current blocker explicit if candidates are missing**

If no `coordinator` or `executor` candidate reaches `high`, write:

```text
blocker -> upstream agent supply gap
```

Place this blocker line inside `## Go / No-Go decision` as its own standalone line, not hidden in prose.

Expected: no fuzzy language like “maybe usable” in the decision section.

### Task 5: Produce the Go / No-Go decision

**Files:**

- Modify: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`

- [ ] **Step 1: Write the decision in fixed format**

Use one of these patterns:

```text
reviewer -> sysarch (high, validated)
coordinator -> <candidate> (high, validated for Phase 2 entry)
executor -> <candidate or no confirmed candidate>
decision -> GO for Phase 2 (coordinator expansion only)
```

or

```text
reviewer -> sysarch (high, validated)
coordinator -> none (no confirmed high-confidence candidate)
executor -> none (no confirmed high-confidence candidate)
decision -> NO-GO
blocker -> upstream agent supply gap
```

- [ ] **Step 2: Add a “recommended next action” section**

If `GO`, specify the next exact subproject: `Phase 2 — coordinator expansion validation`.
If `NO-GO`, specify the next exact subproject: `upstream candidate supply / provisioning`.

- [ ] **Step 3: Verify the report contains no ambiguous completion language**

Check for and remove phrases like:

- “probably”
- “should be fine”
- “seems okay”
- “maybe ready”

Expected: the report ends with a binary decision and named next action.

- [ ] **Step 4: Commit the decision report**

Run:

```bash
git add docs/plans/2026-03-15-phase0-agent-inventory-report.md
git commit -m "docs: conclude phase0 agent inventory"
```

Expected: the report becomes the single source of truth for this Phase 0 execution round.

### Task 6: Propagate only the necessary summary to existing roadmap docs

**Files:**

- Modify: `docs/plans/2026-03-15-phase0-agent-inventory-plan.md`
- Modify: `docs/plans/2026-03-15-real-3-agent-target-plan.md` (only if findings materially change candidate understanding)

- [ ] **Step 1: Add a brief execution status note to the Phase 0 plan**

Append a concise section such as:

- inventory execution date
- result: `GO` or `NO-GO`
- pointer to the full report

- [ ] **Step 2: Update the real 3-agent target plan only if the candidate picture changed**

Examples of justified updates:

- new `coordinator` candidate discovered
- new `executor` candidate discovered
- blocker wording refined from generic to specific

Use this bright-line rule for materiality:

- update the target plan only if a new candidate appears, an existing candidate's confidence changes, or the blocker changes from generic uncertainty to a more specific resource gap
- do not update the target plan for wording-only cleanup that leaves the candidate picture and decision unchanged

If none of the main blockers, candidate availability, confidence levels, or phase-entry decision changed materially, skip this step and leave the file untouched.

- [ ] **Step 3: Verify doc consistency manually**

Re-read the three files together:

- `docs/superpowers/specs/2026-03-15-phase0-agent-inventory-design.md`
- `docs/plans/2026-03-15-phase0-agent-inventory-report.md`
- `docs/plans/2026-03-15-real-3-agent-target-plan.md`

Expected:

- no contradictions about current candidates
- no accidental claim that full 3-agent has started

- [ ] **Step 4: Commit the summary propagation**

Run:

```bash
git add docs/plans/2026-03-15-phase0-agent-inventory-plan.md docs/plans/2026-03-15-real-3-agent-target-plan.md
git commit -m "docs: sync phase0 inventory outcome"
```

If only one file changed, add and commit only that file.

### Task 7: Verify the documentation round before declaring completion

**Files:**

- Verify: `docs/plans/2026-03-15-phase0-agent-inventory-report.md`
- Verify: `docs/plans/2026-03-15-phase0-agent-inventory-plan.md`
- Verify: `docs/plans/2026-03-15-real-3-agent-target-plan.md`

- [ ] **Step 1: Run markdown/error validation**

Use the workspace problems check / Markdown diagnostics for the modified files.

Run with the available tooling for:

- `docs/plans/2026-03-15-phase0-agent-inventory-report.md`
- `docs/plans/2026-03-15-phase0-agent-inventory-plan.md`
- `docs/plans/2026-03-15-real-3-agent-target-plan.md`

This means using the editor's built-in problems diagnostics or the available file error check for these Markdown files before claiming the package is clean.

Expected: no blocking markdown issues.

- [ ] **Step 2: Review git diff for scope discipline**

Run:

```bash
git diff --stat HEAD~1..HEAD
```

or, if multiple commits were made during the plan, inspect the working tree diff before the final commit.
Expected: only the planned docs changed.

- [ ] **Step 3: Record verification evidence in the final handoff note**

Append a final section to `docs/plans/2026-03-15-phase0-agent-inventory-report.md` titled `## Verification Evidence` and write down:

- which commands were run
- whether they succeeded
- what final decision was reached

This step always writes into the report file. If the report changed, include it in the final verification commit in Step 4.

- [ ] **Step 4: Final completion commit**

If verification required one last edit, commit it with a message like:

```bash
git add <changed-files>
git commit -m "docs: verify phase0 inventory package"
```

If the working tree is already clean because verification evidence was captured in an earlier commit, do not create an empty commit.
