# AWS staging execution checklist

This checklist is the last-mile operational companion to:

- `deploy/aws-staging-discovery.md`
- `deploy/aws-staging-rollout-plan.md`
- `deploy/aws-staging.env.example`

It assumes the current live AWS topology confirmed on 2026-03-14:

- public domain: `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com`
- gateway public root already proxies to `127.0.0.1:18789`
- `/feishu/` already proxies to `127.0.0.1:8765`
- legacy three-agent process already occupies `127.0.0.1:9600`

## Deployment target shape

First-pass staging target:

- new sidecar bind: `127.0.0.1:9610`
- public sidecar route: `/sidecar/`
- public base URL:
  - `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar`
- direct runtime invoke:
  - disabled for now (`OPENCLAW_RUNTIME_INVOKE_URL=`)

## 1. Prepare the server directory

On the AWS host:

```bash
mkdir -p /home/ubuntu/openclaw-3agent-sidecar
mkdir -p /home/ubuntu/openclaw-3agent-sidecar/data
mkdir -p /home/ubuntu/openclaw-3agent-sidecar/logs
```

## 2. Sync the repository to the server

One simple option is to clone the repo fresh on the host:

```bash
cd /home/ubuntu
git clone <your-github-url> openclaw-3agent-sidecar
cd /home/ubuntu/openclaw-3agent-sidecar
```

If the repo already exists there, update it instead:

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
git fetch origin
git reset --hard origin/master
```

## 3. Create the Python environment

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

## 4. Create the first-pass `.env`

Start from the example:

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
cp deploy/aws-staging.env.example .env
```

Generate a fresh hooks token:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

Then update `.env` with the generated token.

The first-pass staging shape should remain:

```text
OPENCLAW_HOST=127.0.0.1
OPENCLAW_PORT=9610
OPENCLAW_GATEWAY_BASE_URL=https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com
OPENCLAW_HOOKS_TOKEN=<generated-secret>
OPENCLAW_PUBLIC_BASE_URL=https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar
OPENCLAW_RUNTIME_INVOKE_URL=
```

## 5. Install the systemd user service

Copy the prepared service file:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/systemd/openclaw-sidecar-aws-staging.service ~/.config/systemd/user/openclaw-sidecar.service
systemctl --user daemon-reload
systemctl --user enable openclaw-sidecar.service
systemctl --user restart openclaw-sidecar.service
```

Check status:

```bash
systemctl --user status openclaw-sidecar.service --no-pager
```

## 6. Install the Nginx route

Review the prepared config fragment:

```bash
cat deploy/nginx/openclaw-sidecar-aws-staging.conf
```

Then merge the `location /sidecar/` block into the active server block for:

- `ec2-13-60-187-160.eu-north-1.compute.amazonaws.com`

After editing Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## 7. Verify the local service first

```bash
curl http://127.0.0.1:9610/healthz
curl http://127.0.0.1:9610/readyz
```

Expected:

- health returns `{"status": "ok"}`
- ready returns `{"status": "ready"}`

## 8. Verify the public sidecar path

```bash
curl https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/healthz
curl https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/readyz
```

If TLS or cert verification is still being stabilized, do a temporary test with `-k`, but do not keep that as your final verification habit.

## 9. Validate sidecar integration status

From the repo root on the server:

```bash
. .venv/bin/activate
python -m sidecar.remote_validate
```

First-pass expectations:

- no blocker related to missing `public_base_url`
- no blocker related to missing sidecar public callback path
- `OPENCLAW_RUNTIME_INVOKE_URL` is still intentionally unset

## 10. Do not enable runtime invoke yet

Do **not** fill `OPENCLAW_RUNTIME_INVOKE_URL` until a real upstream HTTP submit endpoint exists.

Live verification on 2026-03-14 showed:

- `POST /invoke` -> `404`
- `POST /runtime/invoke` -> `404`
- `POST /api/runtime/invoke` -> `404`

So an empty `OPENCLAW_RUNTIME_INVOKE_URL` is the correct initial staging state.

## 11. After the first pass succeeds

Only then consider the next step:

1. expose or implement a real upstream invoke endpoint
2. fill `OPENCLAW_RUNTIME_INVOKE_URL`
3. rerun:

```bash
python -m sidecar.remote_validate
python -m sidecar.remote_validate --dispatch-sample
```

## Short version

If you are in a hurry, the minimum safe sequence is:

1. new repo on server
2. `.venv` + `pip install -e .`
3. `.env` from `deploy/aws-staging.env.example`
4. generate fresh `OPENCLAW_HOOKS_TOKEN`
5. run sidecar on `127.0.0.1:9610`
6. publish `/sidecar/` via Nginx
7. run `python -m sidecar.remote_validate`

That gets you a callback-capable staging sidecar without pretending runtime invoke is already solved.
