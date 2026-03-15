# Upstream Candidate Discovery Gate Report

## Scope

This report closes Gate 1 of the upstream candidate supply / provisioning subproject. Its job is to run one short, final discovery window and end with a fixed result shape:

- `found candidate`
- `no additional candidate`
- `inconclusive`

This report does not change live role mapping, does not create new upstream agents, and does not relitigate the full Phase 0 inventory from scratch.

## Entry Baseline

The Gate 1 entry baseline is limited to already validated facts from the Phase 0 inventory round.

- `reviewer -> sysarch`
- `coordinator -> main` (fallback)
- `executor -> main` (fallback)
- confirmed host-visible agents: `main`, `sysarch`
- current blocker: `upstream agent supply gap`
- current honest system label: reviewer-only role-specific routing, not real 3-agent

## Discovery Window

- start date: `2026-03-15`
- execution start timestamp: `2026-03-15T16:50:51.4511749+08:00`
- maximum duration: `<= 1 working day`
- allowed result forms:
  - `found candidate`
  - `no additional candidate`
  - `inconclusive`
- explicit non-goals:
  - no live role mapping change
  - no new experimental deployment
  - no promotion of `main` to a dedicated `coordinator` or `executor` candidate

## Evidence Sources Used

- source: local preflight
- excerpt:
  - `Test-Path C:/git_ssh/openclaw-key-2.pem -> True`
  - `preflight-ok`
  - `{"status": "ready"}`
- contribution: confirmed the preferred SSH key exists locally, the AWS host is reachable, and the sidecar readiness endpoint is serving normally before Gate 1 collection
- disposition: no new information

- source: `ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "curl -s http://127.0.0.1:9600/ops/summary"`
- excerpt:
  - `bridge.agent_id = main`
  - `role_agent_mapping.configured_agents.reviewer = sysarch`
  - `fallback_agent_id = main`
  - `routing_mode = role_specific`
  - `recent_submission.last_submit_status = accepted`
  - `recent_submission.last_result_status = succeeded`
- contribution: confirmed the live routing baseline has not changed since Phase 0; reviewer-only role-specific routing remains active and no additional configured role-specific agent is visible in ops data
- disposition: no new information

- source: `ssh -i C:/git_ssh/openclaw-key-2.pem ubuntu@13.51.172.206 "find /home/ubuntu/.openclaw/agents ... ; ls -lt ..."`
- excerpt:
  - `/home/ubuntu/.openclaw/agents/main`
  - `/home/ubuntu/.openclaw/agents/sysarch`
  - `34ea94c1-2286-4a20-b51d-7eca565115ec.jsonl`
  - `ca888661-cc28-4edb-b344-133add1320fd.jsonl`
- contribution: confirmed the host-visible upstream agent set is still limited to `main` and `sysarch`, with recent session activity for both and no newly surfaced agent directory names
- disposition: no new information

- source: workspace regex search over `docs/**` and `deploy/**` for `coord-|planner-|exec-|worker-|review-|agent.?id`
- excerpt:
  - existing naming families such as `coord-*`, `planner-*`, `exec-*`, `worker-*`, `review-*`
  - existing config placeholders such as `OPENCLAW_COORDINATOR_AGENT_ID`, `OPENCLAW_EXECUTOR_AGENT_ID`, `OPENCLAW_REVIEWER_AGENT_ID`
  - existing known facts such as `OPENCLAW_REVIEWER_AGENT_ID=sysarch` and `work` being invalid
- contribution: surfaced only naming guidance and already-known configuration placeholders; did not add a host-verified new candidate id
- disposition: naming clue only

## Discovery Findings

- The live sidecar routing baseline remains aligned with the Phase 0 report:
  - `reviewer -> sysarch`
  - `coordinator -> main` (fallback)
  - `executor -> main` (fallback)
- `ops/summary` continues to show reviewer-only role-specific routing with `fallback_agent_id = main` and successful recent submission / result status.
- The host-visible upstream agent set remains limited to `main` and `sysarch`; no additional agent directory names were discovered in this Gate 1 pass.
- The workspace naming search produced only naming families and config placeholders already anticipated by the design and rollout docs.
- No evidence in this Gate 1 pass upgraded any naming clue into a real, host-verified new candidate.

## Candidate Qualification Notes

- `main`: already-known fallback agent only; this Gate 1 pass found no new evidence that it should be promoted to a dedicated `coordinator-grade` or `executor-grade` candidate.
- `sysarch`: already-known reviewer baseline; this Gate 1 pass found no new evidence that it should be reclassified as a missing dedicated `coordinator` or `executor` supply answer.
- `coord-*` / `planner-*`: naming clue only; these strings appear in design and roadmap guidance but were not discovered as real host-visible agent ids in this Gate 1 pass.
- `exec-*` / `worker-*`: naming clue only; these strings appear as recommended naming families, not as verified live candidates.
- `review-*`: naming clue only; appears as a naming pattern, not as a new live agent id.

## Gate Result

gate_result -> no additional candidate
candidate -> none
next_action -> Gate 2 provisioning
blocker -> upstream agent supply gap

## Next Action

Gate 2 is required because Gate 1 did not produce enough rollout-grade coverage for coordinator / executor supply.

The active next step is to create the provisioning package that translates the still-open supply gap into:

- candidate supply spec
- naming / mapping draft
- validation entry contract

## Escalation / Inconclusive State

If AWS access or service availability blocks Gate 1 evidence collection, record the blocking condition here and mark the run as `inconclusive` rather than inferring conclusions from stale evidence.

This Gate 1 run did not enter the inconclusive path because the local key check, SSH preflight, and remote `readyz` probe all succeeded.
