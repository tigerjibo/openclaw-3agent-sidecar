# AWS staging rollout plan

This note turns the live AWS findings into an execution plan for bringing `openclaw-3agent-sidecar` online safely.

## Live findings confirmed on 2026-03-14

Confirmed directly on the AWS host:

- SSH host: `ubuntu@13.51.172.206`
- public HTTPS gateway domain: `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com`
- Nginx currently routes:
  - `/feishu/` -> `127.0.0.1:8765`
  - `/` -> `127.0.0.1:18789`
- OpenClaw gateway listens on `127.0.0.1:18789`
- local port `9600` is already occupied by a legacy process:
  - `python3 /tmp/start_three_agent.py`
  - imports `tools.three_agent_system.service_runner`
- the legacy process on `9600` is **not** the new `openclaw-3agent-sidecar` service
- candidate runtime invoke HTTP POST routes on the gateway currently return `404`

Implications:

1. `OPENCLAW_HOOKS_TOKEN` must be **newly generated**.
2. `OPENCLAW_PUBLIC_BASE_URL` does **not** exist yet for the new sidecar.
3. `OPENCLAW_RUNTIME_INVOKE_URL` should remain **unset** until a real upstream HTTP invoke endpoint is implemented or exposed.

## Recommended rollout strategy

Use a staged rollout instead of trying to replace the legacy process in one jump.

### Phase 1 — bring up the new sidecar beside the legacy service

Because `127.0.0.1:9600` is already occupied by the legacy three-agent process, the safest initial port for the new sidecar is a **different local port**, for example:

- `127.0.0.1:9610`

Recommended first-pass service shape:

- new sidecar bind: `127.0.0.1:9610`
- Nginx publish path: `/sidecar/`
- resulting public base URL:
  - `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar`

Repository assets prepared for this rollout:

- `deploy/systemd/openclaw-sidecar-aws-staging.service`
- `deploy/nginx/openclaw-sidecar-aws-staging.conf`

This avoids an immediate collision with the currently running legacy service.

### Phase 2 — publish sidecar callback hooks through Nginx

Add a dedicated Nginx path for the new sidecar, for example:

- `location /sidecar/ { proxy_pass http://127.0.0.1:9610/; }`

Once that route is live, the sidecar callback URLs become:

- `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/hooks/openclaw/ingress`
- `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/hooks/openclaw/result`

At that point, a valid staging value is:

- `OPENCLAW_PUBLIC_BASE_URL=https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar`

### Phase 3 — generate a dedicated hook token

Generate a fresh shared secret:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Use the generated value as:

- `OPENCLAW_HOOKS_TOKEN`

Do not reuse the gateway access token for this purpose.

### Phase 4 — keep runtime invoke disabled until a real endpoint exists

The live check showed:

- `POST /invoke` -> `404`
- `POST /runtime/invoke` -> `404`
- `POST /api/runtime/invoke` -> `404`

That means the current gateway deployment does **not** expose a ready-to-use HTTP submit endpoint for the new sidecar.

So the recommended initial staging config is:

- `OPENCLAW_RUNTIME_INVOKE_URL=`

In other words: bring up the new sidecar first with callback/public routing ready, but **without** direct runtime invoke.

### Phase 5 — decide how invoke should actually work

Before enabling `OPENCLAW_RUNTIME_INVOKE_URL`, choose one of these implementation paths:

1. expose a real HTTP invoke endpoint from the upstream OpenClaw gateway/runtime
2. add a small adapter service that accepts sidecar invoke payloads and forwards them into OpenClaw
3. redesign the integration so staging does not depend on direct runtime invoke yet

Until one of those exists, leaving `OPENCLAW_RUNTIME_INVOKE_URL` empty is the correct and honest configuration.

## Recommended initial staging `.env`

Use this shape for the first live deployment pass:

```text
OPENCLAW_HOST=127.0.0.1
OPENCLAW_PORT=9610
OPENCLAW_DB_PATH=./data/sidecar-staging.db

OPENCLAW_GATEWAY_BASE_URL=https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com
OPENCLAW_HOOKS_TOKEN=<generate-a-new-secret>
OPENCLAW_PUBLIC_BASE_URL=https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar
OPENCLAW_RUNTIME_INVOKE_URL=
```

That configuration is intentionally **callback-ready but invoke-disabled**.

## Suggested Nginx shape

Example direction only:

```nginx
location /sidecar/ {
    proxy_pass http://127.0.0.1:9610/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}
```

## Verification order after deployment

1. local sidecar health:
   - `curl http://127.0.0.1:9610/healthz`
2. public sidecar health through Nginx path
3. sidecar ops summary:
   - ensure callback-related config is visible
4. run:
   - `python -m sidecar.remote_validate`

Expected result for the first pass:

- callback/public routing blockers should be gone
- `OPENCLAW_RUNTIME_INVOKE_URL` will still be intentionally unset
- remote validation may still report local-only or partially configured invoke wiring until the upstream submit endpoint exists

## Practical recommendation

Do **not** try to solve all of this in one cut.

The clean rollout order is:

1. new sidecar on a new local port
2. public Nginx route for sidecar
3. fresh hooks token
4. validation of callback/public path
5. only then implement and enable direct runtime invoke

That sequence minimizes risk and avoids fighting the currently running legacy three-agent process.
