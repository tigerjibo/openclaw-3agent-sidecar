# Operations Runbook

## 1. 适用范围

本 runbook 面向 `openclaw-3agent-sidecar` 的值班同学、接手开发者与部署维护人员。

它重点回答三件事：

1. sidecar 当前是否可接单
2. OpenClaw 上游集成是否可用
3. 当自动修复失败时应先看哪里

## 2. 最常看的接口

### `GET /healthz`

用于判断服务是否健康。

重点字段：

- `status`
  - `ok`
  - `degraded`
  - `failed`
- `agent_health`
  - 角色级运行状态
- `integration.gateway.hook_registration`
  - 当前 hook 自动注册状态

### `GET /readyz`

用于判断服务是否可以继续承接制度化任务流。

重点字段：

- `status`
  - `ready`
  - `warming`
  - `blocked`
- `reason`
  - 例如 `integration=gateway_hook_registration`

### `GET /ops/summary`

用于日常排障总览。

重点字段：

- `operator_guidance`
- `intervention_summary`
- `maintenance.last_cycle`
- `integration.gateway.hook_delivery_status`
- `integration.probe`
- `integration.runtime_invoke.result_callback_ready`

### `GET /runtime/maintenance`

用于查看最近一次 maintenance 周期做了什么。

重点字段：

- `last_cycle.recovery`
- `last_cycle.dispatched_task_ids`
- `last_cycle.hook_registration`

## 3. OpenClaw 集成字段怎么读

### `integration.status`

常见值：

- `local_only`
  - 还没有启用任何上游接线
- `partially_configured`
  - 已配置部分上游能力，但还缺 callback 或 gateway 前置条件
- `gateway_hooks_ready`
  - gateway hooks 已具备基本配置，但 direct runtime invoke 未启用
- `runtime_invoke_ready`
  - direct runtime invoke 与 result callback 均已就绪
- `fully_configured`
  - gateway hooks 与 direct runtime invoke 均已具备完整闭环配置

### `integration.gateway.hook_registration.status`

常见值：

- `not_configured`
  - gateway hooks 还没启用
- `missing_public_base_url`
  - 已配置 gateway/token，但没有配置 `OPENCLAW_PUBLIC_BASE_URL`
- `registered`
  - hook 回调地址已自动注册成功
- `register_failed`
  - 自动注册失败，通常是网络或上游异常
- `register_rejected`
  - 自动注册请求发出去了，但上游未接受

### `integration.runtime_invoke.result_callback_ready`

- `true`
  - sidecar 已能在 outgoing invoke 里附带 `callbacks.result`，上游 runtime 可以直接回打结果
- `false`
  - 仅仅能把 invoke 发出去，**还不能形成真实闭环**

此时继续看：

- `integration.runtime_invoke.result_callback_url`
- `integration.runtime_invoke.missing_requirements`

最常见缺口是：

- `public_base_url`
- `hooks_token`

### `integration.gateway.hook_registration_ready`

- `true`：当前 hook 注册已完成
- `false`：当前仍不能把 hook delivery 当成已就绪

### `integration.gateway.hook_delivery_status`

常见值：

- `not_configured`
- `pending_public_base_url`
- `retry_wait`
- `registered`
- `registration_failed`

这比直接看原始注册状态更适合值班快速判断。

## 4. 自动修复相关字段

### `attempt_count`

表示 hook 自动注册一共尝试了几次。

### `last_attempt_at`

表示最近一次自动注册尝试时间。

### `next_retry_at`

表示下一次允许自动重试的时间窗口。

如果当前已经成功注册，则该字段为 `null`。

## 5. 关键环境变量

### 集成配置

- `OPENCLAW_GATEWAY_BASE_URL`
- `OPENCLAW_HOOKS_TOKEN`
- `OPENCLAW_PUBLIC_BASE_URL`
- `OPENCLAW_RUNTIME_INVOKE_URL`

### 自动修复 / 稳定性

- `OPENCLAW_INTEGRATION_PROBE_TTL_SEC`
- `OPENCLAW_HOOK_REGISTRATION_RETRY_SEC`
- `OPENCLAW_HOOK_REGISTRATION_FAILURE_ALERT_AFTER`

## 6. 常见告警与处理建议

### 场景 A：`missing_public_base_url`

表现：

- `operator_guidance.action == configure_public_base_url`
- `hook_delivery_status == pending_public_base_url`

优先处理：

1. 配置 `OPENCLAW_PUBLIC_BASE_URL`
2. 确认该地址是上游 OpenClaw 可访问的公网/可达地址
3. 重启服务或等待下一轮自动注册

如果同时启用了 `OPENCLAW_RUNTIME_INVOKE_URL`，这一步也会顺带让 direct runtime invoke 的 result callback wiring 变为可用。

### 场景 B：`register_failed`

表现：

- `operator_guidance.action == repair_hook_registration`
- `hook_delivery_status == retry_wait`
- `next_retry_at` 非空

优先处理：

1. 看 `message`
2. 确认 gateway 地址、token、网络、防火墙、DNS
3. 根据 `next_retry_at` 判断是否应等待自动重试还是人工介入

### 场景 C：健康降级且 readiness 被阻断

表现：

- `healthz.status == degraded`
- `readyz.status == blocked`
- `readyz.reason == integration=gateway_hook_registration`

含义：

- hook 自动注册已连续失败到达阈值
- 服务应被视为暂不适合继续接入新的制度化集成流量

优先处理：

1. 修复 gateway 注册失败原因
2. 观察下一次自动重试是否恢复
3. 若确认上游长期不可用，转人工停用该集成链路

### 场景 D：`configure_runtime_callbacks`

表现：

- `operator_guidance.action == configure_runtime_callbacks`
- `integration.runtime_invoke.result_callback_ready == false`
- `integration.runtime_invoke.missing_requirements` 非空

含义：

- sidecar 已能向上游 runtime 发 invoke
- 但还不能让上游把结果安全打回 sidecar

优先处理：

1. 配置 `OPENCLAW_PUBLIC_BASE_URL`
2. 保持 `OPENCLAW_HOOKS_TOKEN` 非空并与上游一致
3. 再看 `GET /ops/summary` 中 `result_callback_ready` 是否转为 `true`

## 7. 启动与部署 Checklist

### 环境变量（必填）

| 变量 | 说明 | 示例 |
| ---- | ---- | ---- |
| `OPENCLAW_DB_PATH` | SQLite 持久化路径 | `/data/sidecar/sidecar.sqlite3` |

### 环境变量（可选 — 集成模式）

| 变量 | 说明 | 示例 |
| ---- | ---- | ---- |
| `OPENCLAW_GATEWAY_BASE_URL` | OpenClaw gateway 地址 | `https://openclaw.example.com` |
| `OPENCLAW_HOOKS_TOKEN` | Hook 鉴权 token | `secret-token-xxx` |
| `OPENCLAW_PUBLIC_BASE_URL` | Sidecar 对外可达地址 | `https://sidecar.example.com` |
| `OPENCLAW_RUNTIME_INVOKE_URL` | Runtime invoke 端点 | `https://openclaw.example.com/invoke` |

补充说明：

- 若只配置 `OPENCLAW_RUNTIME_INVOKE_URL`，sidecar 只能“把活发出去”，不能算完整可回写闭环
- 要让 direct runtime invoke 达到真实闭环，需要同时配置 `OPENCLAW_PUBLIC_BASE_URL` 与 `OPENCLAW_HOOKS_TOKEN`

### 启动命令

```bash
# Linux / macOS
OPENCLAW_DB_PATH=/data/sidecar/sidecar.sqlite3 python -m sidecar

# Windows PowerShell
$env:OPENCLAW_DB_PATH='C:\data\sidecar\sidecar.sqlite3'; python -m sidecar
```

若只想快速确认真实 HTTP invoke/result 闭环是否还活着，可直接运行：

```bash
openclaw-sidecar-smoke
```

它会启动一个临时 sidecar + fake runtime，对外打印 JSON 摘要，适合作为交接、演示或值班快速自检。

### 健康检查

- `GET /healthz` — 返回 `{"status": "ok"}` 即为健康
- `GET /readyz` — 返回 `{"status": "ready"}` 即可接单
- `GET /ops/summary` — 完整运维总览

若启用了 runtime invoke，还应额外确认：

- `ops.integration.runtime_invoke.result_callback_ready == true`

否则说明“只接上了半条线”。

### 常见启动失败排查

| 现象 | 检查 |
| ---- | ---- |
| 启动后 healthz 返回 failed | 检查 DB 路径是否可写 |
| readyz 返回 blocked | 检查集成环境变量和 gateway 可达性 |
| hook 注册持续失败 | 检查 `OPENCLAW_GATEWAY_BASE_URL` / `OPENCLAW_HOOKS_TOKEN` / 网络 |

## 8. 数据生命周期与 TTL 策略

### 当前行为

- 任务和事件数据持久化在 SQLite 中，不会自动过期
- 已完结的任务（`done` / `cancelled`）会一直保留

### 推荐运维策略

- 每 30 天归档或清理已完结超过 30 天的任务和事件
- 归档前先备份 SQLite 文件：`cp sidecar.sqlite3 sidecar.sqlite3.bak`
- 清理 SQL（仅在确认备份后执行）：

```sql
DELETE FROM task_events WHERE task_id IN (
    SELECT task_id FROM tasks
    WHERE state IN ('done', 'cancelled')
    AND updated_at < datetime('now', '-30 days')
);
DELETE FROM tasks
WHERE state IN ('done', 'cancelled')
AND updated_at < datetime('now', '-30 days');
VACUUM;
```

## 9. 本地 Smoke 验证流程

每次部署后，按以下步骤验证：

1. 启动服务：`python -m sidecar`
2. 检查健康：`curl http://127.0.0.1:9600/healthz`
3. 检查就绪：`curl http://127.0.0.1:9600/readyz`
4. 检查运维总览：`curl http://127.0.0.1:9600/ops/summary`
5. 若配置了集成，检查 hook 注册状态是否为 `registered`
6. 若配置了 `OPENCLAW_RUNTIME_INVOKE_URL`，检查 `integration.runtime_invoke.result_callback_ready` 是否符合预期
7. 若以上均正常，部署验证通过

### 自动化验证命令

```bash
pytest tests -q
python -m compileall sidecar
openclaw-sidecar-smoke
```

## 10. 值班口径建议

对外可简单说：

> sidecar 当前既会报告任务流是否健康，也会报告与 OpenClaw 上游的接线是否已经失稳；当 hook 注册连续失败时，服务会明确降级并阻断 readiness，而不是静默假装一切正常。
