# AWS role-specific agent staging rollout checklist

This checklist is the execution companion for enabling and validating
**role-specific OpenClaw CLI agents** on the current AWS staging host.

It is intentionally narrower than the broader rollout documents:

- `deploy/aws-staging-safe-deploy.md`
- `deploy/aws-staging-execution-checklist.md`
- `deploy/aws-direct-cutover-impact-and-runbook.md`
- `docs/plans/2026-03-15-role-specific-agent-staging-validation.md`

Use this checklist only after the CLI bridge implementation is already present in
`master` and you are ready to validate real role-based agent routing on the host.

Validated on 2026-03-15 with the following minimal successful shape:

- `OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://main`
- `OPENCLAW_REVIEWER_AGENT_ID=sysarch`
- `OPENCLAW_COORDINATOR_AGENT_ID=`
- `OPENCLAW_EXECUTOR_AGENT_ID=`

This reviewer-only shape completed a real task closed loop on the AWS host and is
the recommended first-pass rollout shape.

---

## 1. Goal

Enable and verify the following behavior on AWS staging:

- `coordinator` can use `OPENCLAW_COORDINATOR_AGENT_ID`
- `executor` can use `OPENCLAW_EXECUTOR_AGENT_ID`
- `reviewer` can use `OPENCLAW_REVIEWER_AGENT_ID`
- any missing role-specific value still falls back to the default agent encoded in:
  - `OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://main`

Success means:

1. sidecar remains healthy
2. CLI bridge remains callback-capable
3. real staging validation proves the new role mapping does not break submit/result flow

---

## 2. Preconditions

Do not start this rollout unless all of the following are true:

- [ ] You can SSH into `ubuntu@13.51.172.206`
- [ ] The repo exists at `/home/ubuntu/openclaw-3agent-sidecar`
- [ ] The service is managed from that repo, not `/home/ubuntu/openclaw`
- [ ] The installed code includes the role-routing commits
- [ ] `openclaw` CLI is available to the service user
- [ ] You know the real upstream agent ids you want to test
- [ ] You have a rollback window and someone can watch health during the change

If any of these are false, stop here and fix them first.

---

## 3. Confirm current remote baseline

### 3.1 Confirm repo version

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
git fetch origin
git rev-parse --short HEAD
git log --oneline -5
```

Expected recent commits include:

- `189190f` — role-specific agent configuration groundwork
- `6cf372f` — route CLI bridge by sidecar role
- `3027599` — release note template
- `8d83d62` — CLI bridge iteration release note
- `4193b58` — role-specific agent staging validation note

### 3.2 Confirm current env

```bash
grep -E '^(OPENCLAW_RUNTIME_INVOKE_URL|OPENCLAW_COORDINATOR_AGENT_ID|OPENCLAW_EXECUTOR_AGENT_ID|OPENCLAW_REVIEWER_AGENT_ID|OPENCLAW_PUBLIC_BASE_URL|OPENCLAW_HOOKS_TOKEN)=' /home/ubuntu/openclaw-3agent-sidecar/.env
```

Expected before rollout:

- `OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://main`
- role-specific env vars may be empty or missing
- `OPENCLAW_PUBLIC_BASE_URL` and `OPENCLAW_HOOKS_TOKEN` should already be valid if real callback validation is expected

### 3.3 Confirm service health before any change

```bash
systemctl --user status openclaw-sidecar.service --no-pager
curl http://127.0.0.1:9600/healthz
curl http://127.0.0.1:9600/readyz
curl http://127.0.0.1:9600/ops/summary
```

Go / no-go:

- go only if `healthz.status=ok`
- go only if `readyz.status=ready`
- go only if the service is already stable before editing `.env`

---

## 4. Back up before editing anything

### 4.1 Back up `.env`

```bash
cp /home/ubuntu/openclaw-3agent-sidecar/.env /home/ubuntu/openclaw-3agent-sidecar/.env.bak.$(date +%Y%m%dT%H%M%S)
```

### 4.2 Snapshot service status and recent logs

```bash
systemctl --user status openclaw-sidecar.service --no-pager > /home/ubuntu/openclaw-3agent-sidecar/logs/pre-role-routing-status.txt
journalctl --user -u openclaw-sidecar.service -n 200 --no-pager > /home/ubuntu/openclaw-3agent-sidecar/logs/pre-role-routing-journal.txt
```

### 4.3 Optional: snapshot current ops summary

```bash
curl -s http://127.0.0.1:9600/ops/summary > /home/ubuntu/openclaw-3agent-sidecar/logs/pre-role-routing-ops-summary.json
```

---

## 5. Edit `.env` for role-specific routing

Open this file only:

- `/home/ubuntu/openclaw-3agent-sidecar/.env`

Set or update the following keys:

```text
OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://main
OPENCLAW_COORDINATOR_AGENT_ID=<real-coordinator-agent-id>
OPENCLAW_EXECUTOR_AGENT_ID=<real-executor-agent-id>
OPENCLAW_REVIEWER_AGENT_ID=<real-reviewer-agent-id>
```

### Recommended first-pass strategy

Start with the smallest meaningful change:

#### Option A — reviewer-only first (lowest risk)

```text
OPENCLAW_COORDINATOR_AGENT_ID=
OPENCLAW_EXECUTOR_AGENT_ID=
OPENCLAW_REVIEWER_AGENT_ID=<real-reviewer-agent-id>
```

Use this when you want to prove role-specific routing works without changing the planner/executor path first.

This option has already been verified successfully on the current AWS staging host.

#### Option B — coordinator + reviewer first

```text
OPENCLAW_COORDINATOR_AGENT_ID=<real-coordinator-agent-id>
OPENCLAW_EXECUTOR_AGENT_ID=
OPENCLAW_REVIEWER_AGENT_ID=<real-reviewer-agent-id>
```

Use this if the reviewer-only step succeeds and you want broader coverage while still keeping executor on fallback.

#### Option C — all three roles

```text
OPENCLAW_COORDINATOR_AGENT_ID=<real-coordinator-agent-id>
OPENCLAW_EXECUTOR_AGENT_ID=<real-executor-agent-id>
OPENCLAW_REVIEWER_AGENT_ID=<real-reviewer-agent-id>
```

Use this only after you are confident the upstream agents are all present and stable.

Do not assume any historical agent id is still valid. During the 2026-03-15 validation:

- `main` was valid
- `sysarch` was valid
- `work` returned `Unknown agent id` and should not be used until re-confirmed

---

## 6. Restart and verify configuration load

### 6.1 Restart the service

```bash
systemctl --user restart openclaw-sidecar.service
systemctl --user status openclaw-sidecar.service --no-pager
```

### 6.2 Check for immediate startup failures

```bash
journalctl --user -u openclaw-sidecar.service -n 200 --no-pager
```

Stop immediately if you see:

- CLI not found
- import / startup exceptions
- port bind failures
- repeated callback auth errors at startup

### 6.3 Re-check local endpoints

```bash
curl http://127.0.0.1:9600/healthz
curl http://127.0.0.1:9600/readyz
curl http://127.0.0.1:9600/ops/summary
```

Expected:

- `healthz.status=ok`
- `readyz.status=ready`
- `ops.summary.integration.runtime_invoke.bridge.role_agent_mapping` is visible

If the bridge metadata is missing or the service is not ready, do not continue to sample dispatch.

---

## 7. Validate with remote_validate

### 7.1 Probe-only first

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
. .venv/bin/activate
python -m sidecar.remote_validate
```

If the formal staging service is already running on `127.0.0.1:9600`, avoid port conflicts by temporarily overriding:

```bash
OPENCLAW_PORT=0 \
OPENCLAW_DB_PATH=/tmp/openclaw-sidecar-remote-validate.sqlite3 \
python -m sidecar.remote_validate
```

Expected:

- no fatal `config_blockers`
- no fatal `probe_blockers`
- callback requirements look complete when real runtime submission is intended

### 7.2 Real dispatch sample second

```bash
python -m sidecar.remote_validate --dispatch-sample
```

Likewise, when the formal service is already running:

```bash
OPENCLAW_PORT=0 \
OPENCLAW_DB_PATH=/tmp/openclaw-sidecar-remote-validate.sqlite3 \
python -m sidecar.remote_validate --dispatch-sample
```

Check in the JSON output:

- `ok`
- `blocking_issue_groups.dispatch_blockers`
- `blocking_issue_groups.result_blockers`
- `ops.integration.runtime_invoke.recent_submission`

---

## 8. What to verify in ops summary

Inspect:

- `integration.runtime_invoke.bridge.role_agent_mapping.configured_agents`
- `integration.runtime_invoke.bridge.role_agent_mapping.fallback_agent_id`
- `integration.runtime_invoke.bridge.role_agent_mapping.routing_mode`
- `integration.runtime_invoke.recent_submission.last_submit_status`
- `integration.runtime_invoke.recent_submission.last_error_kind`
- `integration.runtime_invoke.recent_submission.last_recovery_action`

Expected:

- configured roles are shown honestly
- fallback agent remains `main`
- routing mode is `role_specific` when at least one role-specific agent is configured

---

## 9. How to prove the selected agent actually changed

Because the runtime bridge now records `selected_agent_id`, prefer this evidence order:

1. `remote_validate --dispatch-sample` output
2. `ops.summary.integration.runtime_invoke.recent_submission`
3. `journalctl --user -u openclaw-sidecar.service`
4. upstream CLI/runtime logs if needed

On the 2026-03-15 reviewer-only validation, the strongest proof came from the upstream session log under:

- `/home/ubuntu/.openclaw/agents/sysarch/sessions/*.jsonl`

where the reviewer invoke id appeared as:

- `inv:task-req-live-role-routing-check-001:reviewer:v5:a3`

If you still need stronger proof, temporarily grep recent logs for the agent id you just enabled.

---

## 10. Pass criteria

Treat the rollout as successful only if all are true:

- [ ] service restarts cleanly
- [ ] `/healthz` is `ok`
- [ ] `/readyz` is `ready`
- [ ] role mapping appears correctly in `ops/summary`
- [ ] `remote_validate` probe-only passes without new critical blockers
- [ ] `remote_validate --dispatch-sample` completes without callback or result failure
- [ ] no role enters a repeated `submit_failed` / `blocked` loop after the change

---

## 11. Immediate rollback

Rollback immediately if any of these happen:

- callback failures start right after enabling role-specific ids
- one role repeatedly fails while fallback previously worked
- sidecar health degrades or readiness blocks
- logs show invalid / missing upstream agent ids
- `remote_validate --dispatch-sample` fails in a way attributable to the new mapping

### Rollback steps

1. Restore the previous `.env`

```bash
cp /home/ubuntu/openclaw-3agent-sidecar/.env.bak.<timestamp> /home/ubuntu/openclaw-3agent-sidecar/.env
```

1. Or simply clear role-specific overrides:

```text
OPENCLAW_COORDINATOR_AGENT_ID=
OPENCLAW_EXECUTOR_AGENT_ID=
OPENCLAW_REVIEWER_AGENT_ID=
```

1. Restart the service

```bash
systemctl --user restart openclaw-sidecar.service
```

1. Re-check:

```bash
curl http://127.0.0.1:9600/healthz
curl http://127.0.0.1:9600/readyz
python -m sidecar.remote_validate
```

1. If any tasks were blocked by the failed rollout, inspect whether manual unblock is required after recovery.

---

## 12. Short operator version

If you only need the shortest safe execution path:

1. SSH into the host
2. back up `/home/ubuntu/openclaw-3agent-sidecar/.env`
3. set `OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://main`
4. enable one role-specific agent first (prefer reviewer)
5. restart `openclaw-sidecar.service`
6. check `/healthz`, `/readyz`, `/ops/summary`
7. run `python -m sidecar.remote_validate`
8. run `python -m sidecar.remote_validate --dispatch-sample`
9. if anything breaks, clear the role-specific env vars and restart

That is the smallest honest staging rollout for role-specific CLI agent routing.
