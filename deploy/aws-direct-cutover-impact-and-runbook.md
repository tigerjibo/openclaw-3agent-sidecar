# AWS direct cutover impact assessment and runbook

This document is for the **direct replacement** strategy requested by the operator:

> do not run the new sidecar in parallel for an extended period; replace the current legacy 3-agent runtime on the AWS host and repair forward if issues appear.

It uses the live AWS findings confirmed on 2026-03-14 and turns them into a **bounded cutover plan**.

## Executive summary

A direct cutover is possible **only if its scope is explicitly limited**.

What can be directly replaced:

- the legacy local 3-agent runtime process currently occupying `127.0.0.1:9600`
- the old `tools.three_agent_system.service_runner` behavior behind that local process

What cannot honestly be claimed as already replaceable by the current sidecar:

- the full legacy Feishu bot service on `/feishu/`
- the existing daily / evening / weekly timed automation jobs
- the older single-agent operational workflows already wired under `/home/ubuntu/openclaw`

So the safe interpretation of **direct replacement** is:

> replace the legacy local 3-agent runtime process in one cut, while deliberately keeping the old Feishu bot and old timed jobs in place until they are migrated separately.

If you instead redirect all old Feishu traffic or timed pipelines into the sidecar on the same day, the cutover becomes a **feature gap migration**, not a simple process replacement.

## Live AWS facts this plan depends on

Confirmed directly on the host:

- public domain: `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com`
- gateway public root currently proxies to `127.0.0.1:18789`
- `/feishu/` currently proxies to `127.0.0.1:8765`
- a legacy process currently occupies `127.0.0.1:9600`
  - command source: `/tmp/start_three_agent.py`
  - imports `tools.three_agent_system.service_runner`
- the current host still runs old timed jobs such as:
  - `openclaw-evening-review.timer`
  - `openclaw-ops-daily-brief.timer`
  - `openclaw-suggestion-daily.timer`
  - `openclaw-wechat-metrics-daily.timer`
  - multiple user crontab jobs under `/home/ubuntu/openclaw`
- candidate gateway runtime invoke POST endpoints currently return `404`

Implication:

- the sidecar is currently suitable to replace the **legacy 9600 local 3-agent runtime**
- it is **not yet a drop-in replacement** for the old Feishu bot or the older scheduled content/report automation stack

## Scope of this direct cutover

### In scope

Directly cut over these responsibilities:

- local task kernel runtime
- local 3-role state machine runtime
- local dispatcher / scheduler / recovery / health loop
- local HTTP control plane on the port currently used by legacy `three_agent_system`

### Explicitly out of scope

Do **not** treat these as replaced during this cutover:

- `/feishu/` public routing
- `openclaw-feishu-bot.service`
- `openclaw-evening-review.timer`
- `openclaw-ops-daily-brief.timer`
- other report / publish / governance timers
- legacy cron jobs under the `ubuntu` user crontab

## Impact assessment by concern

### 1. Will morning / evening reports be affected?

If you keep the old timers and old Feishu bot untouched, the answer is:

- **No, not directly.**

Those jobs still belong to the old system today and are not driven by the new sidecar.

If you stop or rewrite those timers during the same cutover window, the answer becomes:

- **Yes, they may fail immediately.**

That is why this runbook requires keeping those timers in place during the first direct cutover.

### 2. Will the old single-agent still run?

Partially yes.

After this cutover:

- the legacy local process on `127.0.0.1:9600` should stop
- old single-agent-oriented timed jobs may still continue running if you do not disable them
- the old Feishu bot may still continue running if `/feishu/` is left unchanged

So the old system is **not fully retired** by this cutover. Only the legacy 3-agent runtime slice is retired.

### 3. Who handles Feishu after the cutover?

For the first direct cutover, Feishu should still be handled by the existing old bot path:

- `/feishu/` -> `127.0.0.1:8765`

Reason:

- the current sidecar exposes hook endpoints such as `/hooks/openclaw/ingress` and `/hooks/openclaw/result`
- but it does **not** currently provide the same public Feishu bot surface as the old bot server

Therefore, **do not** move `/feishu/` to the sidecar during this cutover.

### 4. After cutover, can tasks run in parallel?

Need to distinguish two meanings of “parallel”.

#### Single task internal flow

Still **serial**:

- `coordinator -> executor -> reviewer`

The sidecar does not run these three roles in parallel within one task.

#### Multiple tasks in the system

Yes, multiple tasks can be in-flight and scheduled across the runtime.

However, real upstream HTTP invoke wiring is still incomplete on the live gateway, so production-scale concurrency still depends on completing that upstream integration path.

## Direct cutover rules

These rules are mandatory for this strategy.

### Rule 1 — replace the 9600 process, not the whole old platform

The direct replacement target is the legacy runtime process on `127.0.0.1:9600`.

It is **not** the entire `/home/ubuntu/openclaw` deployment.

### Rule 2 — keep old timers and Feishu routing unchanged during the cutover window

Do not change:

- `/feishu/` Nginx routing
- user crontab jobs
- old report / review / governance timers

### Rule 3 — keep rollback assets before stopping the legacy runtime

Before touching the running legacy runtime, capture:

- old process info
- old `.env`
- old service/unit file references
- current timers list
- current crontab

### Rule 4 — use a maintenance window

This is a hard cut. Perform it only inside a declared window with someone watching health checks and logs.

## Pre-cutover checklist

Complete these checks before stopping the legacy runtime.

### Capture current runtime facts

```bash
echo '=== 9600 owner ==='
ss -tlnp | grep 9600 || true
ps -fp $(ss -tlnp | awk '/127.0.0.1:9600/ {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | head -n 1) || true
pwdx $(ss -tlnp | awk '/127.0.0.1:9600/ {print $NF}' | sed -E 's/.*pid=([0-9]+).*/\1/' | head -n 1) || true
```

### Back up old config and service references

```bash
cp /home/ubuntu/openclaw/.env /home/ubuntu/openclaw/.env.bak.$(date +%Y%m%dT%H%M%S)
crontab -l > /home/ubuntu/openclaw/exports/crontab.backup.$(date +%Y%m%dT%H%M%S)
systemctl --user list-timers --all --no-pager > /home/ubuntu/openclaw/exports/systemd-timers.backup.$(date +%Y%m%dT%H%M%S)
systemctl --user list-units --type=service --all --no-pager > /home/ubuntu/openclaw/exports/systemd-services.backup.$(date +%Y%m%dT%H%M%S)
```

### Confirm what remains untouched

Before cutover, reconfirm:

- `/feishu/` still points to `127.0.0.1:8765`
- old report timers are still present
- old crontab remains unchanged

## Recommended direct cutover implementation shape

Even for a hard cut, keep the new repo in its own directory:

- `/home/ubuntu/openclaw-3agent-sidecar`

That gives you a clean rollback target while still allowing a **non-parallel runtime cutover**.

Recommended first direct-cutover runtime shape:

- stop legacy process on `127.0.0.1:9600`
- start `openclaw-sidecar` on `127.0.0.1:9600`
- keep `/feishu/` untouched
- keep old timers untouched
- keep `OPENCLAW_RUNTIME_INVOKE_URL=` empty unless a real endpoint exists

## Direct cutover steps

### 1. Prepare the new sidecar fully before touching the legacy runtime

```bash
mkdir -p /home/ubuntu/openclaw-3agent-sidecar
cd /home/ubuntu/openclaw-3agent-sidecar
# clone or update repo here
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
cp deploy/aws-staging.env.example .env
```

Edit `.env` so the port is the legacy runtime port:

```text
OPENCLAW_HOST=127.0.0.1
OPENCLAW_PORT=9600
OPENCLAW_DB_PATH=./data/sidecar-cutover.db
OPENCLAW_GATEWAY_BASE_URL=https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com
OPENCLAW_HOOKS_TOKEN=<generated-secret>
OPENCLAW_PUBLIC_BASE_URL=
OPENCLAW_RUNTIME_INVOKE_URL=
OPENCLAW_DEFAULT_RUNTIME_MODE=three_agent_active
```

Notes:

- `OPENCLAW_PUBLIC_BASE_URL` may remain empty if this cutover is only replacing the local runtime slice and not publishing sidecar hooks yet
- `OPENCLAW_RUNTIME_INVOKE_URL` should remain empty until the upstream submit endpoint exists
- if you want a gentler first pass, use `three_agent_shadow` instead of `three_agent_active`

### 2. Verify the sidecar starts locally before final cutover

You can do a short foreground smoke start on another temporary port first, then switch it back to `9600` before cutover.

### 3. Stop the legacy 9600 process

Use the actual process/service owner found during pre-check.

The key acceptance condition is simple:

```bash
ss -tlnp | grep 9600 || echo PORT_9600_FREE
```

### 4. Start the new sidecar on 9600

```bash
mkdir -p ~/.config/systemd/user
cp /home/ubuntu/openclaw-3agent-sidecar/deploy/systemd/openclaw-sidecar-aws-staging.service ~/.config/systemd/user/openclaw-sidecar.service
systemctl --user daemon-reload
systemctl --user enable openclaw-sidecar.service
systemctl --user restart openclaw-sidecar.service
```

Before restarting, update the service file so it points to:

- `WorkingDirectory=/home/ubuntu/openclaw-3agent-sidecar`
- `EnvironmentFile=/home/ubuntu/openclaw-3agent-sidecar/.env`
- port `9600` via the `.env`

### 5. Validate the replacement locally

```bash
curl http://127.0.0.1:9600/healthz
curl http://127.0.0.1:9600/readyz
curl http://127.0.0.1:9600/ops/summary
```

Expected:

- `healthz.status=ok`
- `readyz.status=ready`
- `ops.integration.status=local_only` or another honest non-failing state

### 6. Validate the untouched legacy surfaces still exist

```bash
systemctl --user list-timers --all --no-pager | grep -E 'evening-review|daily-brief|suggestion-daily|wechat-metrics' || true
sudo nginx -T | grep -nE 'location /feishu/|proxy_pass http://127.0.0.1:8765' || true
```

Expected:

- old timers still listed
- `/feishu/` still points to `127.0.0.1:8765`

### 7. Observe for one maintenance interval

After startup, inspect:

```bash
journalctl --user -u openclaw-sidecar.service -n 200 --no-pager
curl http://127.0.0.1:9600/runtime/maintenance
```

If health stays clean and no unexpected blocked state appears, the direct runtime cutover is complete.

## Stop conditions

Abort and roll back immediately if any of these appear:

- `/healthz` fails on `127.0.0.1:9600`
- `/readyz` returns blocked
- `openclaw-sidecar` cannot hold port `9600`
- old timed jobs disappear or start failing because of this cutover
- `/feishu/` route changes unexpectedly
- operators discover old business workflows were implicitly depending on the stopped legacy 9600 process

## Rollback sequence

If the cutover fails, do this in order.

### 1. Stop the sidecar

```bash
systemctl --user stop openclaw-sidecar.service
```

### 2. Restore the old legacy runtime process/service

Restart the previously captured legacy runtime owner.

### 3. Reconfirm port 9600

```bash
ss -tlnp | grep 9600 || true
```

### 4. Reconfirm old external surfaces

```bash
systemctl --user list-timers --all --no-pager | grep -E 'evening-review|daily-brief|suggestion-daily|wechat-metrics' || true
sudo nginx -T | grep -nE 'location /feishu/|proxy_pass http://127.0.0.1:8765' || true
```

### 5. Keep the new sidecar repo for debugging

Do not delete `/home/ubuntu/openclaw-3agent-sidecar` after rollback. It should remain as the forensic/debug workspace.

## Honest recommendation

If the operator insists on direct replacement, this runbook is the lowest-risk version of that strategy.

But the evidence still says the same thing:

- direct replacement is acceptable for the **legacy 9600 3-agent runtime slice**
- direct replacement is **not yet justified** for the full old Feishu + scheduled-jobs platform

That boundary should be treated as non-negotiable until the sidecar actually owns those missing capabilities.
