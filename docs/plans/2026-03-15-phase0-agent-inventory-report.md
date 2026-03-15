# Phase 0 Agent Inventory Report

## Scope

This report records the Phase 0 upstream agent inventory for AWS staging, using only evidence-backed observations to support a binary go / no-go decision for real 3-agent rollout entry.

## Current staging baseline

In this report, `role -> agent` means the currently configured role-to-agent routing observed in staging.

- `reviewer -> sysarch`
- `coordinator -> main`
- `executor -> main`
- known visible agents: `main`, `sysarch`
- known invalid historical candidate: `work`

## Evidence collection log

### 2026-03-15T14:30:17.1787407+08:00 — sidecar baseline health and routing

- command: SSH to `ubuntu@13.51.172.206` and query `http://127.0.0.1:9600/healthz`, `http://127.0.0.1:9600/readyz`, and `http://127.0.0.1:9600/ops/summary`
- `healthz.status = ok`
- `readyz.status = ready`
- `ops.status = ok`
- `ops.integration.status = runtime_invoke_ready`
- `ops.integration.runtime_invoke.bridge.kind = openclaw_cli`
- `ops.integration.runtime_invoke.bridge.agent_id = main`
- `ops.integration.runtime_invoke.bridge.role_agent_mapping.configured_agents.reviewer = sysarch`
- `ops.integration.runtime_invoke.bridge.role_agent_mapping.fallback_agent_id = main`
- `ops.integration.runtime_invoke.bridge.role_agent_mapping.routing_mode = role_specific`
- `ops.integration.runtime_invoke.recent_submission.last_submit_status = accepted`
- `ops.integration.runtime_invoke.recent_submission.last_result_status = succeeded`

### 2026-03-15T14:30:32.2528329+08:00 — host-visible agent inventory and recent sessions

- command: SSH to `ubuntu@13.51.172.206` and inspect `/home/ubuntu/.openclaw/agents`, recent `*.jsonl` session files, and `openclaw agent list`
- visible agent directories: `main`, `sysarch`
- recent session evidence observed under `main/sessions/*.jsonl`
- recent session evidence observed under `sysarch/sessions/ca888661-cc28-4edb-b344-133add1320fd.jsonl`
- no additional agent directory names were observed in the directory listing returned by `find /home/ubuntu/.openclaw/agents -maxdepth 1 -mindepth 1 -type d`
- `openclaw agent list` from the non-login shell returned `bash: line 1: openclaw: command not found`

### 2026-03-15T14:30:46.5472755+08:00 — absolute-path CLI listing attempt

- command: SSH to `ubuntu@13.51.172.206` and run `/home/ubuntu/.npm-global/bin/openclaw agent list`
- result: the binary executed, but returned `error: required option '-m, --message <text>' not specified`
- interpretation: this did not produce an agent inventory; it indicates `agent list` is not a supported listing form for this CLI entrypoint

### 2026-03-15T14:31:03.0004087+08:00 — CLI help confirmation

- command: SSH to `ubuntu@13.51.172.206` and run `/home/ubuntu/.npm-global/bin/openclaw agent --help`
- observed CLI version banner: `OpenClaw 2026.3.2 (85377a2)`
- observed subcommand shape: `openclaw agent` is an invoke-style command requiring `-m, --message <text>`
- no agent-listing capability was shown in the help output
- inventory evidence therefore remains limited to directory and session discovery, plus previously validated runtime behavior

### 2026-03-15T14:32:20.0023482+08:00 — session sample and role evidence

- command: SSH to `ubuntu@13.51.172.206` and inspect the head of `sysarch/sessions/ca888661-cc28-4edb-b344-133add1320fd.jsonl`
- observed session header timestamp: `2026-02-21T11:17:14.048Z`
- observed session workspace: `/home/ubuntu/.openclaw/workspace-sysarch`
- observed prompt content in the sampled session includes `Role: reviewer`
- this sampled session supports the already validated reviewer-oriented use of `sysarch`; it does not add a new coordinator or executor candidate

### 2026-03-15T14:33:01.0739761+08:00 — latest session modification times

- command: SSH to `ubuntu@13.51.172.206` and list latest files under `main/sessions` and `sysarch/sessions`
- latest `main` session files observed in the directory listing:
	- `34ea94c1-2286-4a20-b51d-7eca565115ec.jsonl` modified at `2026-03-15 06:11:43.347543808 +0000`
	- `5c34d037-1e41-44bf-ba51-81f611a30732.jsonl` modified at `2026-03-15 03:49:14.051722824 +0000`
- latest `sysarch` session file observed in the directory listing:
	- `ca888661-cc28-4edb-b344-133add1320fd.jsonl` modified at `2026-03-15 03:11:04.431242031 +0000`
- recent-session evidence is therefore current for both `main` and `sysarch` on the same UTC day as this inventory run

## Candidate inventory table

Candidate inventory rows will be added after fresh AWS evidence collection confirms current agent visibility, recent sessions, and invokeability signals.

| agent_id | source_of_truth | recent_session_seen | invokeable | suggested_role | confidence | notes |
| --- | --- | --- | --- | --- | --- | --- |

## Role classification notes

Role classification notes will be added only after fresh evidence is collected and compared against the approved confidence rules.

## Confidence ratings

Confidence ratings will be assigned as `high`, `medium`, or `low` based on the approved Phase 0 design thresholds defined in `docs/superpowers/specs/2026-03-15-phase0-agent-inventory-design.md`.

## Go / No-Go decision

A binary decision will be recorded here after the inventory evidence and candidate classification are complete.

## Recommended next action

- if `GO`: `Phase 2 — coordinator expansion validation`
- if `NO-GO`: `upstream candidate supply / provisioning`
