# Role-Specific Agent Staging Validation Note

> 记录日期：2026-03-15
>
> 目标：对 `openclaw-3agent-sidecar` 的 role-specific CLI agent routing 做真实 staging 验证。

---

## 当前结论

本次验证**已完成 reviewer-only 的 staging 真实验证**。

已确认：

- 本地实现、定向测试和全量测试均已通过
- 已使用 SSH 登录 AWS 主机并同步远端部署副本到最新代码
- 正式运行的 sidecar 服务在 `127.0.0.1:9600` 上保持健康
- 远端 `ops/summary` 已显示：
  - `role_agent_mapping.configured_agents.reviewer = sysarch`
  - `fallback_agent_id = main`
  - `routing_mode = role_specific`
- 在正式运行的 sidecar 服务上创建真实任务后，任务成功按：
  - `coordinator -> executor -> reviewer -> done`
  闭环完成
- 远端 OpenClaw 会话日志证明 reviewer 轮次实际进入了：
  - `/home/ubuntu/.openclaw/agents/sysarch/sessions/...jsonl`
  - 对应 invoke id：`inv:task-req-live-role-routing-check-001:reviewer:v5:a3`

因此，当前状态应被标记为：

- **代码已就绪**
- **reviewer-only role-specific staging 验证已通过**
- **当前不是完整 3-agent rollout，只是 3 角色流程 + reviewer 独立 agent**
- **若继续扩大 rollout，可再逐步启用 coordinator / executor 的独立 agent**

配套执行步骤见：

- `deploy/aws-role-specific-agent-reviewer-only.env.example`
- `deploy/aws-role-specific-agent-staging-rollout-checklist.md`

---

## 本次真实验证结果摘要（SSH 恢复后）

### 已验证通过的配置

```text
OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://main
OPENCLAW_COORDINATOR_AGENT_ID=
OPENCLAW_EXECUTOR_AGENT_ID=
OPENCLAW_REVIEWER_AGENT_ID=sysarch
```

### 已验证通过的 agent

- `main` ✅
- `sysarch` ✅

### 当前准确口径

- sidecar 内部一直是固定 `coordinator / executor / reviewer` 三角色流程
- 但 AWS staging 上当前只验证了 `reviewer -> sysarch`
- `coordinator` / `executor` 仍走 fallback `main`
- 因而当前不是“3 个角色都已切到各自独立 upstream agent”的完整 3-agent 形态

### 当前不应直接使用的候选

- `work` ❌
  - 远端 CLI 返回：`Unknown agent id "work"`

### 已确认的闭环行为

- `coordinator` 继续走 fallback agent `main`
- `executor` 继续走 fallback agent `main`
- `reviewer` 成功切换到 `sysarch`
- 真实任务最终进入 `done`

### 本次额外发现

- 远端部署目录 `/home/ubuntu/openclaw-3agent-sidecar` 是运行副本，不是 git 仓库；需要用归档/同步方式更新代码
- 当正式 sidecar 已占用 `9600` 时，`python -m sidecar.remote_validate` 需要临时覆盖：
  - `OPENCLAW_PORT=0`
  - `OPENCLAW_DB_PATH=/tmp/openclaw-sidecar-remote-validate.sqlite3`
  否则会因为端口冲突失败

---

## 已观测到的阻塞

### 1. SSH 登录失败（首次尝试时）

实际结果：

- `ssh ubuntu@13.51.172.206` 返回 `Permission denied (publickey)`

含义：

- 当前工作站不具备访问该主机所需的 SSH 私钥或授权
- 因而无法直接检查远端：
  - `/home/ubuntu/openclaw-3agent-sidecar/.env`
  - 当前运行提交
  - systemd 服务状态
  - 远端 `remote_validate` 结果

### 2. 公网 sidecar 接口超时（首次尝试时）

从当前工作站对以下地址进行探测时，均返回超时：

- `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/healthz`
- `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/readyz`
- `https://ec2-13-60-187-160.eu-north-1.compute.amazonaws.com/sidecar/ops/summary`

含义：

- 当前无法从此工作站确认：
  - Nginx `/sidecar/` 路由是否可达
  - 远端 sidecar 服务是否健康
  - ops summary 是否已经暴露 role-specific routing 信息

这不等于远端服务一定异常，也可能是：

- 访问源网络受限
- 目标站点仅在特定网络范围可达
- 反向代理或安全组对当前来源做了限制
- 远端服务当前确实未对外正常暴露

---

## SSH 恢复后建议立即执行的最短验证

> 本节已被本次 reviewer-only staging 验证实际走通，可继续作为后续 coordinator / executor rollout 的操作模板。

### 1. 确认远端代码版本

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
git fetch origin
git rev-parse --short HEAD
git log --oneline -3
```

目标：确认远端至少包含以下提交：

- `189190f` — role-specific agent configuration groundwork
- `6cf372f` — route CLI bridge by sidecar role
- `3027599` — release note template
- `8d83d62` — CLI bridge iteration release note

### 2. 检查关键环境变量

```bash
grep -E '^(OPENCLAW_RUNTIME_INVOKE_URL|OPENCLAW_COORDINATOR_AGENT_ID|OPENCLAW_EXECUTOR_AGENT_ID|OPENCLAW_REVIEWER_AGENT_ID|OPENCLAW_PUBLIC_BASE_URL|OPENCLAW_HOOKS_TOKEN)=' /home/ubuntu/openclaw-3agent-sidecar/.env
```

目标：确认以下两类信息：

1. 是否已启用 CLI bridge，例如：
   - `OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://main`
2. 是否已配置 role-specific agents，例如：
   - `OPENCLAW_COORDINATOR_AGENT_ID=...`
   - `OPENCLAW_EXECUTOR_AGENT_ID=...`
   - `OPENCLAW_REVIEWER_AGENT_ID=...`

### 3. 检查 sidecar 服务状态

```bash
systemctl --user status openclaw-sidecar.service --no-pager
journalctl --user -u openclaw-sidecar.service -n 200 --no-pager
```

目标：确认：

- 服务正在运行
- 没有明显的配置错误 / CLI 找不到 / callback 401 / timeout

### 4. 本机直连 health / ready / ops

```bash
curl http://127.0.0.1:9600/healthz
curl http://127.0.0.1:9600/readyz
curl http://127.0.0.1:9600/ops/summary
```

若 staging 仍使用独立端口，则改为对应实际端口。

重点看：

- `status`
- `integration.status`
- `integration.runtime_invoke.bridge`
- `integration.runtime_invoke.recent_submission`

### 5. 运行远端 validate

```bash
cd /home/ubuntu/openclaw-3agent-sidecar
. .venv/bin/activate
python -m sidecar.remote_validate
python -m sidecar.remote_validate --dispatch-sample
```

重点看：

- `blocking_issue_groups`
- `dispatch_blockers`
- `result_blockers`
- 是否出现 `callback_failed:*`
- 是否出现 `result_failed:*`

### 6. 验证 role-specific agent 是否真正生效

若 `ops/summary` 中可见 `integration.runtime_invoke.bridge.role_agent_mapping`，应确认：

- `configured_agents.coordinator`
- `configured_agents.executor`
- `configured_agents.reviewer`
- `fallback_agent_id`
- `routing_mode`

若再触发一次真实 sample dispatch，还应确认最近一次提交摘要中能反映新的路由结果；如需更细粒度证据，应结合日志查找 `selected_agent_id` 或相应 CLI 调用记录。

---

## 通过标准

满足以下条件时，可判定 role-specific agent staging 验证通过：

1. sidecar 服务健康可达
2. `remote_validate` probe-only 无关键 blocker
3. `remote_validate --dispatch-sample` 能完成真实提交
4. 未配置某角色 agent 时，仍能 fallback 到 `main`
5. 已配置某角色 agent 时，ops / 日志能证明其实际参与路由
6. 未出现持续 `submit_failed` / `blocked` / callback 401 / callback timeout

---

## 若验证失败，优先排查顺序

1. SSH / 主机访问条件是否恢复
2. `/home/ubuntu/openclaw-3agent-sidecar/.env` 中的 role-specific agent 配置是否正确
3. `openclaw` CLI 在远端是否可执行
4. `OPENCLAW_PUBLIC_BASE_URL` 与 `OPENCLAW_HOOKS_TOKEN` 是否匹配
5. `ops/summary.integration.runtime_invoke.recent_submission`
6. `journalctl --user -u openclaw-sidecar.service`

---

## 当前建议

当前最准确表述应为：

> role-specific agent routing 已在 AWS staging 完成 reviewer-only 真实验证：`reviewer -> sysarch` 已跑通，`coordinator/executor` 继续安全回退到 `main`。如需继续放量，建议按同样方式逐步验证 coordinator / executor 的独立 agent，而不是一次性全量切换。
