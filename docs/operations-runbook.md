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

### `GET /runtime/maintenance`

用于查看最近一次 maintenance 周期做了什么。

重点字段：

- `last_cycle.recovery`
- `last_cycle.dispatched_task_ids`
- `last_cycle.hook_registration`

## 3. OpenClaw 集成字段怎么读

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

## 7. 最小验证命令

每次做完关键改动后，至少执行：

- `pytest tests -q`
- `python -m compileall sidecar`

## 8. 值班口径建议

对外可简单说：

> sidecar 当前既会报告任务流是否健康，也会报告与 OpenClaw 上游的接线是否已经失稳；当 hook 注册连续失败时，服务会明确降级并阻断 readiness，而不是静默假装一切正常。
