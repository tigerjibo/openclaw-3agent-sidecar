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

## 7. CLI bridge 常见故障排查

当 `OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://...` 时，值班排障建议优先按下面顺序看，避免一上来就翻整份日志：

1. `openclaw-sidecar-remote-validate`

   先看 `blocking_issue_groups`；如果要验证真实 submit，再跑 `--dispatch-sample`。

1. `GET /ops/summary`

   重点看 `integration.runtime_invoke.bridge`、`integration.runtime_invoke.recent_submission`、`integration.probe.runtime_invoke`。

1. 最近一次 runtime submit 的结构化错误

   重点看 `last_error_kind`、`last_error_message`、`last_recovery_action`。

1. 最后再看进程级 stderr / stdout 摘要和上游日志

### 场景 E：CLI not found

表现：

- `integration.probe.runtime_invoke.kind == configuration_error`
- `message` 或 `last_error_message` 包含 `OpenClaw CLI not found`
- `submission_recovery_action == block`

含义：

- sidecar 已尝试走 CLI bridge
- 但目标主机上没有可执行的 `openclaw`，或 `OPENCLAW_RUNTIME_CLI_BIN` / PATH 指向错误

优先处理：

1. 在服务所在主机确认 `openclaw` 可执行文件存在且当前服务账号可访问
2. 检查 PATH 或 `OPENCLAW_RUNTIME_CLI_BIN` 是否正确
3. 重跑 `openclaw-sidecar-remote-validate`
4. 如任务已被 block，修复后再人工解阻

### 场景 F：callback 401

表现：

- `blocking_issue_groups.result_blockers` 包含 `dispatch_sample=callback_failed:client_error`
- 最近一次 submit 的 `last_error_kind == client_error`
- 错误详情中带 `stage=callback`、`http_status=401`

含义：

- CLI 本体已经跑完
- 但上游回打 `POST /hooks/openclaw/result` 时，被 sidecar 鉴权拒绝

优先处理：

1. 检查 `OPENCLAW_HOOKS_TOKEN` 是否与上游使用的 token 一致
2. 确认 callback URL 指向的是当前 sidecar 暴露的真实地址
3. 再跑 `openclaw-sidecar-remote-validate --dispatch-sample`

### 场景 G：callback timeout

表现：

- 最近一次 submit 的 `last_error_kind == timeout`
- 且错误详情带 `stage=callback`
- `result_callback_ready == true`，但 dispatch sample 仍失败

含义：

- sidecar 已把 callback contract 发给上游
- 但回调链路在网络、反向代理或 sidecar 本地处理环节超时

优先处理：

1. 确认 `OPENCLAW_PUBLIC_BASE_URL` 对上游真实可达
2. 检查反向代理、Nginx、负载均衡和防火墙
3. 查看 sidecar 访问日志与上游 callback 请求日志
4. 若确认只是偶发超时，再看 submit retry/backoff 是否正在收口重试

### 场景 H：malformed role output

表现：

- `blocking_issue_groups.result_blockers` 包含 `dispatch_sample=result_failed:payload_error` 或 `schema_error`
- `recent_submission.last_result_status == failed`
- `last_error_kind` 可能为空，但 runtime response 里的 `result_error_kind` 已指明失败类型

含义：

- CLI 命令本身执行成功
- 但 agent 返回的内容不是 sidecar 角色要求的 JSON，或 reviewer/coordinator/executor 的输出 schema 不合格

优先处理：

1. 先看 `result_error_kind`
2. 再看 `result_error_message`
3. 检查对应角色 prompt / 上游 agent 配置是否被改坏
4. 若是 reviewer 决策字段非法，重点排查 `review_decision`

### 场景 I：runtime stderr 非空 / exit code 非零

表现：

- `last_error_kind == runtime_error`
- 最近一次 submit 或异常详情中带 `exit_code`
- `stderr_excerpt` / `stdout_excerpt` 可见明确报错

含义：

- `openclaw agent --agent ... --json` 已真正启动
- 但进程以非零退出码返回，或 stderr 明确说明了上游 runtime 执行失败

优先处理：

1. 先看 `exit_code`
2. 再看 `stderr_excerpt`
3. 若 stderr 为空，再看 `stdout_excerpt`
4. 确认目标 agent id、权限、工作目录与依赖是否正常

### 最小排障顺序（建议背下来）

1. 先看 `remote_validate` 的 `blocking_issue_groups`
2. 再看 `ops.summary.integration.runtime_invoke.recent_submission`
3. 再看 `integration.probe.runtime_invoke`
4. 最后再翻完整 sidecar / upstream 日志

## 8. 启动与部署 Checklist

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

若要验证**真实上游 / staging** 接线，而不是 fake runtime，可运行：

```bash
openclaw-sidecar-remote-validate
```

默认会读取项目根目录下的 `.env` 作为 `OPENCLAW_*` 配置来源；如果 shell 里已显式导出同名环境变量，则以 shell 值为准。

如果希望在探测成功后再真正向远端 runtime 发起一次样例提交，可改用：

```bash
openclaw-sidecar-remote-validate --dispatch-sample
```

重点关注输出中的：

- `ok`
- `blocking_issues`
- `blocking_issue_groups.config_blockers`
- `blocking_issue_groups.probe_blockers`
- `blocking_issue_groups.dispatch_blockers`
- `blocking_issue_groups.result_blockers`
- `ops.integration.status`
- `ops.integration.runtime_invoke.result_callback_ready`
- `ops.integration.probe`

若 `ok=false`，优先按 `blocking_issues` 收口，不要直接把 staging 问题归咎于 sidecar 内核。

推荐值班顺序：

1. 先看 `config_blockers`，确认是不是接线没配全
2. 再看 `probe_blockers`，判断是不是 upstream 根本不可达
3. 如果用了 `--dispatch-sample`，再看 `dispatch_blockers`
4. 最后看 `result_blockers`，区分 callback 失败、role 输出失败等“活发出去了但没闭环”的问题

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

## 9. 数据生命周期与 TTL 策略

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

## 10. 本地 Smoke 验证流程

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
openclaw-sidecar-remote-validate
```

## 11. 值班口径建议

对外可简单说：

> sidecar 当前既会报告任务流是否健康，也会报告与 OpenClaw 上游的接线是否已经失稳；当 hook 注册连续失败时，服务会明确降级并阻断 readiness，而不是静默假装一切正常。
