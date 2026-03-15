# AWS staging discovery guide

This note explains how to discover the three missing integration values for `openclaw-3agent-sidecar` when the upstream OpenClaw runtime is hosted on AWS.

Target values:

- `OPENCLAW_HOOKS_TOKEN`
- `OPENCLAW_PUBLIC_BASE_URL`
- `OPENCLAW_RUNTIME_INVOKE_URL`

## Live verification result on 2026-03-14

These findings were confirmed directly on the AWS host during a live check:

- SSH host works: `ubuntu@13.51.172.206`
- Nginx public domain is:
  - `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com`
- Nginx currently routes:
  - `/feishu/` -> `127.0.0.1:8765`
  - `/` -> `127.0.0.1:18789`
- OpenClaw gateway listens on `127.0.0.1:18789`
- local port `9600` is already occupied by a legacy `tools.three_agent_system.service_runner` process
- the new `openclaw-3agent-sidecar` service is **not** currently deployed on the host
- `POST /invoke`, `POST /runtime/invoke`, and `POST /api/runtime/invoke` all returned `404` when tested locally against the gateway

This means:

1. `OPENCLAW_HOOKS_TOKEN` still needs to be **generated**.
2. `OPENCLAW_PUBLIC_BASE_URL` for the new sidecar does **not** exist yet.
3. `OPENCLAW_RUNTIME_INVOKE_URL` should stay **unset** until a real upstream HTTP submit endpoint exists.

## What is already known

From the historical OpenClaw runbook and deployment notes, the current highest-confidence upstream clues are:

- AWS host candidate: `13.51.172.206`
- historical gateway bind: `127.0.0.1:18789`
- historical public forwarder: `:18780`
- current bot env clue in old repo: `OPENCLAW_BOT_URL=http://13.51.172.206:8765`
- current callback examples seen in the old runbook:
  - `http://13.51.172.206/feishu/event`
  - `http://13.51.172.206/feishu/card`

These clues are useful, but they do **not** fully determine the sidecar values. You still need one short verification pass on the AWS host.

## Quick answer: where to look

### `OPENCLAW_HOOKS_TOKEN`

This value was **not** found as an existing standard variable in the old OpenClaw repository.

Recommended approach:

1. Treat it as a new shared secret for sidecar hook authentication.
2. Generate a fresh value on the AWS host or locally.
3. Store the same value in the sidecar config and any upstream component that must call the sidecar hooks.

Generate one safely:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Do **not** blindly reuse:

- `gateway.auth.token`
- `OPENCLAW_GATEWAY_TOKEN`

Those appear to be gateway access/auth settings, not sidecar hook callback credentials.

### `OPENCLAW_PUBLIC_BASE_URL`

This value is the **externally reachable base URL of the sidecar itself**.

Typical forms:

- `https://sidecar.example.com`
- `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar`
- `http://13.51.172.206:9610`

You should confirm it from:

1. reverse proxy config (`nginx`, `caddy`, etc.)
2. sidecar service bind/port
3. AWS security group exposure

### `OPENCLAW_RUNTIME_INVOKE_URL`

This value is the upstream HTTP endpoint that accepts sidecar invoke submissions.

It was **not** explicitly documented in the old repository. That means you must confirm it from:

1. gateway service / runtime service configuration
2. reverse proxy routes
3. a small live probe against candidate paths

Common candidates to test:

- `http://13.51.172.206/invoke`
- `http://13.51.172.206/runtime/invoke`
- `http://13.51.172.206/api/runtime/invoke`
- `http://13.51.172.206:18780/invoke`
- `http://13.51.172.206:18780/runtime/invoke`
- `http://13.51.172.206:18780/api/runtime/invoke`

However, note the live result above: the currently deployed gateway returned `404` to POST requests on these candidate invoke paths, so they should be treated as probes, not assumed values.

## Recommended server-side discovery steps

SSH to the AWS host and run the following from `/home/ubuntu/openclaw`.

### 1. Inspect env clues

```bash
cd /home/ubuntu/openclaw
grep -E 'BOT_URL|PUBLIC|SIDECAR|OPENCLAW' .env || true
```

This often reveals:

- existing public URLs
- bot URLs
- sidecar-like hostnames
- old or partial staging hints

### 2. Inspect gateway services

```bash
systemctl --user status openclaw-gateway.service --no-pager
systemctl --user status openclaw-gateway-forwarder.service --no-pager

systemctl --user cat openclaw-gateway.service
systemctl --user cat openclaw-gateway-forwarder.service 2>/dev/null || true
```

Look for:

- bind port (`18789`)
- public forward port (`18780`)
- custom proxy/forward args
- environment files or additional drop-ins

### 3. Inspect listening ports

```bash
ss -tlnp | grep -E '18789|18780|8765|9600'
```

Interpretation:

- `127.0.0.1:18789` usually means internal gateway bind
- `0.0.0.0:18780` usually means public forwarder
- `0.0.0.0:9600` would suggest sidecar is directly exposed
- `0.0.0.0:8765` is usually the bot, not the sidecar runtime callback URL

### 4. Inspect reverse proxy routes if present

```bash
sudo nginx -T | grep -nE 'server_name|listen|location|proxy_pass|18789|18780|8765|9600|invoke|feishu|sidecar' || true
```

Look for:

- `location /sidecar`
- `proxy_pass http://127.0.0.1:9600`
- `location /invoke`
- `location /runtime/invoke`
- any route that forwards to the gateway/runtime submit handler

### 5. Probe candidate invoke URLs

```bash
for url in \
  http://13.51.172.206/invoke \
  http://13.51.172.206/runtime/invoke \
  http://13.51.172.206/api/runtime/invoke \
  http://13.51.172.206:18780/invoke \
  http://13.51.172.206:18780/runtime/invoke \
  http://13.51.172.206:18780/api/runtime/invoke
do
  echo "--- $url"
  curl -sS -i --max-time 5 "$url" | head -20
done
```

Desired outcome:

- one route returns a meaningful method/auth/application response
- instead of a generic `404`, timeout, or unrelated HTML page

## How to decide the final values

### Pick `OPENCLAW_HOOKS_TOKEN`

If no existing sidecar hook secret is documented, generate a new one and use it consistently.

### Pick `OPENCLAW_PUBLIC_BASE_URL`

Choose the public address that the upstream runtime can actually call.

Examples:

- if reverse proxy exposes sidecar under `/sidecar`, use `http://13.51.172.206/sidecar`
- if sidecar is exposed directly on `9600`, use `http://13.51.172.206:9600`
- if a real domain exists, prefer that over raw IPs

### Pick `OPENCLAW_RUNTIME_INVOKE_URL`

Choose the route that matches the real upstream submit endpoint discovered by service config or probe.

Examples:

- `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/runtime/invoke`
- `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/api/runtime/invoke`
- `https://gateway.example.com/api/runtime/invoke`

If the live gateway returns `404` for all candidate POST routes, the correct value is not “pick one anyway” — it is to leave `OPENCLAW_RUNTIME_INVOKE_URL` unset until the upstream endpoint is really implemented.

## Final verification after filling `.env`

Once the values are known, update the sidecar env and run:

```bash
python -m sidecar.remote_validate
python -m sidecar.remote_validate --dispatch-sample
```

The first command should clear configuration blockers.
The second command should only be used when you intentionally want to hit the real upstream runtime.

## Practical rule of thumb

- `HOOKS_TOKEN`: usually **generated**, not discovered
- `PUBLIC_BASE_URL`: usually discovered from **reverse proxy / public bind**
- `RUNTIME_INVOKE_URL`: usually discovered from **gateway/runtime route config + live probe**

## What to do next

If you are rolling out the new sidecar onto the current AWS host, follow `deploy/aws-staging-rollout-plan.md`.
