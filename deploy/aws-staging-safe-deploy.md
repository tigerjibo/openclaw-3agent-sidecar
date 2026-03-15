# AWS staging safe deploy guide

This guide focuses on one goal:

> deploy the new `openclaw-3agent-sidecar` on AWS **without overwriting** the existing `/home/ubuntu/openclaw/.env` used by the current production-like system.

## Safety rule

Never edit this file during the first-pass sidecar rollout:

- `/home/ubuntu/openclaw/.env`

Always use this separate file for the new sidecar:

- `/home/ubuntu/openclaw-3agent-sidecar/.env`

## Why this is safe

The current AWS host already runs older services from:

- `/home/ubuntu/openclaw`

The new sidecar rollout should use a separate directory:

- `/home/ubuntu/openclaw-3agent-sidecar`

That separation protects:

- the old `.env`
- the old runtime process tree
- the old DB and bot/gateway wiring

## Safe deployment sequence

### 1. Confirm the old `.env` exists

```bash
test -f /home/ubuntu/openclaw/.env && echo OLD_ENV_PRESENT
```

### 2. Back up the old `.env` anyway

```bash
cp /home/ubuntu/openclaw/.env /home/ubuntu/openclaw/.env.bak.$(date +%Y%m%dT%H%M%S)
```

This step should not be needed for the new sidecar itself, but it gives you an easy rollback anchor if someone edits the wrong file later.

### 3. Create a separate directory for the new sidecar

```bash
mkdir -p /home/ubuntu/openclaw-3agent-sidecar
mkdir -p /home/ubuntu/openclaw-3agent-sidecar/data
mkdir -p /home/ubuntu/openclaw-3agent-sidecar/logs
```

### 4. Put the new repo there

```bash
cd /home/ubuntu
git clone <your-github-url> openclaw-3agent-sidecar
```

Or, if the directory already exists:

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
git fetch origin
git reset --hard origin/master
```

### 5. Create the new sidecar `.env` from the new repo only

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
cp deploy/aws-staging.env.example .env
```

This is the critical safety boundary:

- copy from: `/home/ubuntu/openclaw-3agent-sidecar/deploy/aws-staging.env.example`
- write to: `/home/ubuntu/openclaw-3agent-sidecar/.env`
- do **not** write to: `/home/ubuntu/openclaw/.env`

### 6. Back up the new sidecar `.env` before editing it

```bash
cp /home/ubuntu/openclaw-3agent-sidecar/.env /home/ubuntu/openclaw-3agent-sidecar/.env.bak.$(date +%Y%m%dT%H%M%S)
```

### 7. Edit only the new sidecar `.env`

Only modify:

- `/home/ubuntu/openclaw-3agent-sidecar/.env`

Expected first-pass key fields:

```text
OPENCLAW_HOST=127.0.0.1
OPENCLAW_PORT=9610
OPENCLAW_GATEWAY_BASE_URL=https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com
OPENCLAW_HOOKS_TOKEN=<generated-secret>
OPENCLAW_PUBLIC_BASE_URL=https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar
OPENCLAW_RUNTIME_INVOKE_URL=
```

### 8. Install the venv inside the new directory

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

### 9. Install the new sidecar service

```bash
mkdir -p ~/.config/systemd/user
cp /home/ubuntu/openclaw-3agent-sidecar/deploy/systemd/openclaw-sidecar-aws-staging.service ~/.config/systemd/user/openclaw-sidecar.service
systemctl --user daemon-reload
systemctl --user enable openclaw-sidecar.service
systemctl --user restart openclaw-sidecar.service
```

### 10. Verify the service uses the new directory

```bash
systemctl --user cat openclaw-sidecar.service
```

You should see paths under:

- `/home/ubuntu/openclaw-3agent-sidecar`

and **not**:

- `/home/ubuntu/openclaw`

### 11. Verify the new sidecar locally

```bash
curl http://127.0.0.1:9610/healthz
curl http://127.0.0.1:9610/readyz
```

### 12. Add the Nginx `/sidecar/` route

Merge the prepared fragment from:

- `deploy/nginx/openclaw-sidecar-aws-staging.conf`

Then reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 13. Verify the public sidecar path

```bash
curl https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/healthz
curl https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/readyz
```

### 14. Validate the new sidecar config

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
. .venv/bin/activate
python -m sidecar.remote_validate
```

## Red flags: stop immediately if you see these

Stop and re-check if any command targets:

- `/home/ubuntu/openclaw/.env`
- `/home/ubuntu/openclaw/.venv`
- `/home/ubuntu/openclaw` as the new sidecar working directory

Those paths belong to the existing system and should not be used for the first-pass sidecar rollout.

## One-line safety summary

If the path starts with `/home/ubuntu/openclaw-3agent-sidecar`, you are probably safe.

If the path starts with `/home/ubuntu/openclaw`, slow down and check whether you are touching the old system by mistake.
