# Adapter Contract

`openclaw-3agent-sidecar` 目前已经实现了可运行的 `ingress -> invoke -> result`
适配层闭环。本文档描述的是**当前代码真实成立的 contract**，用于指导：

- sidecar 与官方 OpenClaw 的真实接线
- HTTP runtime invoke / result callback 集成
- CLI bridge 集成
- staging / operations 场景下的排障与验证

这不是未来设想稿；它应尽量与当前代码、测试和运维行为保持同步。

---

## 1. 总体边界

官方 OpenClaw 与 sidecar 的责任分工如下：

### 官方 OpenClaw 负责

- gateway
- webhook / routing
- workspace / skills
- session / agent runtime

### sidecar 负责

- `tasks` / `task_events` 任务真相源
- `coordinator / executor / reviewer` 三角色状态机
- invoke payload 生成
- result 回写与状态推进
- recovery / scheduler / health / ops summary

### 关键原则

1. 不修改官方 OpenClaw 核心源码
2. sidecar task kernel 是任务状态真相源
3. OpenClaw session 不是 task state truth
4. 外宣可用“明制小内阁”叙事，但 contract、代码、测试必须坚持：
   - `coordinator`
   - `executor`
   - `reviewer`

---

## 2. 三段式 contract 概览

当前 sidecar 采用如下三段式 contract：

1. **Ingress**
   - 把制度化任务送入 task kernel
2. **Invoke**
   - sidecar 为某个 role 生成稳定 invoke payload，并提交给 HTTP runtime 或 CLI runtime bridge
3. **Result**
   - 上游 runtime 以结构化 payload 回写 role result，sidecar 再推进状态机

其中，HTTP 集成与 CLI bridge 都应最终收敛到同一套 result contract。

---

## 3. Ingress Contract

### 3.1 支持的入口

当前代码已支持两类 HTTP 入口：

- `POST /runtime/ingress`
- `POST /hooks/openclaw/ingress`

区别如下：

#### `/runtime/ingress`

- 用于 runtime 风格的本地/内网接入
- 当前实现不要求 hooks token
- 更适合 sidecar 所在主机或受控上游直接提交

#### `/hooks/openclaw/ingress`

- 用于 OpenClaw hook 风格接入
- 当配置 `OPENCLAW_HOOKS_TOKEN` 时，必须提供：
  - `X-OpenClaw-Hooks-Token`
- 更适合走统一 hook 鉴权链路的上游接入

### 3.2 最小必填字段

`IngressAdapter.ingest()` 当前要求以下字段非空：

- `request_id`
- `entrypoint`
- `source`
- `title`
- `message`

并且：

- `entrypoint` 当前仅支持：`institutional_task`

若缺字段或 entrypoint 不支持，当前实现会直接报错。

### 3.3 当前允许字段

除必填字段外，当前实现还会消费以下字段：

- `source_user_id`
- `source_message_id`
- `source_chat_id`
- `task_type_hint`
- `priority_hint`
- `risk_level_hint`
- `trace_id`
- `metadata`

### 3.4 幂等语义

Ingress 以 `request_id` 作为幂等键。

当前行为：

- 若 `request_id` 首次出现：
  - 创建新任务
  - 写入 `task_events`
  - 返回 `{created: True, task_id, task}`
- 若 `request_id` 已存在：
  - 不重复创建任务
  - 返回已有任务 `{created: False, task_id, task}`

也就是说，真实上游必须把 `request_id` 视为**制度化任务创建请求的稳定幂等键**。

### 3.5 trace_id 规则

当前行为：

- 若 ingress payload 提供 `trace_id`：沿用该值
- 若未提供：sidecar 自动生成 UUID

该 `trace_id` 会进入任务元数据，并在后续 invoke / result 流程中继续使用。

### 3.6 task_id 规则

当前 `task_id` 由 `request_id` 派生：

- 非字母数字字符会被标准化为 `-`
- 最终形如：`task-<normalized-request-id>`

因此：

- `request_id` 应稳定
- 上游不应自行直接指定 `task_id`

### 3.7 Ingress 示例

```json
{
  "request_id": "req-openclaw-20260315-001",
  "source": "openclaw",
  "source_user_id": "user-runtime",
  "entrypoint": "institutional_task",
  "title": "为 sidecar 梳理真实接线 contract",
  "message": "请把真实 OpenClaw 集成 contract 明确下来。",
  "task_type_hint": "engineering",
  "trace_id": "trace-openclaw-001",
  "metadata": {
    "channel": "openclaw",
    "deliver_back": true
  }
}
```

---

## 4. Invoke Contract

### 4.1 角色范围

当前 sidecar 只支持三种 role：

- `coordinator`
- `executor`
- `reviewer`

任何其他 role 都应视为不受支持。

### 4.2 当前 invoke payload 字段

`AgentInvokeAdapter.build_invoke()` 当前会生成如下字段：

- `invoke_id`
- `task_id`
- `role`
- `agent_id`
- `trace_id`
- `session_key`
- `goal`
- `input`
- `constraints`

#### 字段说明

##### `invoke_id`

格式：

- `inv:{task_id}:{role}:v{task_version}:a{next_attempt}`

它是单次 role turn 的稳定调用标识，也是 result 回写的幂等键。

##### `task_id`

- 当前任务 ID

##### `role`

- 当前待执行角色

##### `agent_id`

- 当前 payload 中仍写 role 名本身
- 真正提交给 CLI bridge 时，可再按配置映射到：
  - `OPENCLAW_COORDINATOR_AGENT_ID`
  - `OPENCLAW_EXECUTOR_AGENT_ID`
  - `OPENCLAW_REVIEWER_AGENT_ID`
- 若未配置，继续 fallback 到 `openclaw-cli://<default-agent>`

##### `trace_id`

- 由任务 metadata 中的 trace_id 继承而来
- 真实 result callback 必须回显同一个 trace_id

##### `session_key`

- 当前形如：`task:{task_id}:{role}`

##### `goal`

- 角色级固定目标文案

##### `input`

当前包含：

- `title`
- `message`
- `task_context`
- `recent_events`

其中：

- `task_context` 是任务当前字段快照
- 若某些字段以 JSON 字符串存储，会在这里尽量解析成列表/结构
- `recent_events` 当前取最近 10 条事件，按时间顺序供上游角色参考

##### `constraints`

当前包含：

- `timeout_seconds`
- `deliver`
- `structured_output_required`

### 4.3 HTTP runtime invoke contract

当使用 `HttpOpenClawRuntimeBridge` 时，sidecar 会把 invoke payload POST 到配置的：

- `OPENCLAW_RUNTIME_INVOKE_URL`

如果当前 runner 已具备 callback 条件，还会自动补入：

```json
{
  "callbacks": {
    "result": {
      "url": "https://<public-or-local>/hooks/openclaw/result",
      "headers": {
        "X-OpenClaw-Hooks-Token": "<hooks token>"
      }
    }
  }
}
```

#### `callbacks.result` 注入规则

当前行为：

- 若没有可用 `result_callback_url`：不注入 callback contract
- 若有 callback URL：注入 `callbacks.result.url`
- 若同时存在 `hooks_token`：再注入
  - `callbacks.result.headers.X-OpenClaw-Hooks-Token`

这允许上游 runtime 在同一条 invoke 提交中获得 callback 契约，而不依赖额外的带外配置。

### 4.4 CLI bridge invoke contract

当使用 `CliOpenClawRuntimeBridge` 时：

- sidecar 不直接等待外部系统回调 result
- 而是本地执行：
  - `openclaw agent --agent <agent_id> --message <message> --json`
- 再由 CLI bridge 解析角色输出，并主动 POST 回 sidecar 的 result callback

#### CLI bridge 对 invoke payload 的硬要求

当前要求 payload 中必须存在：

- `invoke_id`
- `task_id`
- `role`
- `trace_id`
- `callbacks.result.url`

缺少这些字段会被视为配置或 payload 错误。

### 4.5 上游角色输出要求

当前 contract 要求上游最终返回**严格 JSON 对象**，并按 role 满足对应 schema。

#### coordinator

```json
{
  "goal": "string",
  "acceptance_criteria": ["string"],
  "risk_notes": ["string"],
  "proposed_steps": ["string"]
}
```

#### executor

```json
{
  "result_summary": "string",
  "evidence": ["string"],
  "open_issues": ["string"],
  "followup_notes": ["string"]
}
```

#### reviewer

```json
{
  "review_decision": "approve|reject",
  "review_comment": "string",
  "reasons": ["string"],
  "required_rework": ["string"],
  "residual_risk": "string"
}
```

---

## 5. Result Contract

### 5.1 支持的 result 入口

当前已支持：

- `POST /runtime/result`
- `POST /hooks/openclaw/result`

区别如下：

#### `/runtime/result`

- runtime 风格入口
- 当前实现不要求 hooks token

#### `/hooks/openclaw/result`

- hook 风格入口
- 当配置 `OPENCLAW_HOOKS_TOKEN` 时，必须通过：
  - `X-OpenClaw-Hooks-Token`

### 5.2 最小必填字段

`ResultAdapter.apply_result()` 当前要求以下字段非空：

- `invoke_id`
- `task_id`
- `role`
- `status`
- `trace_id`

此外：

- `output` 可为空对象，但是否能成功推进状态机，取决于 role-specific schema 需求

### 5.3 trace_id 校验

当前行为：

- 若任务存在 trace_id：result payload 中的 `trace_id` 必须与任务 trace_id 完全一致
- 不一致时直接报错

因此：

- 上游 result callback 必须回显原 invoke 的 trace_id

### 5.4 result 幂等语义

当前以 `invoke_id` 作为 result 幂等键。

行为如下：

- 若 `invoke_id` 首次出现：正常应用 result，并推进状态机
- 若 `invoke_id` 已出现：
  - 不重复推进状态机
  - 直接返回任务当前状态

因此：

- `invoke_id` 必须被视为单次 role turn 的稳定 result idempotency key

### 5.5 `status` 语义

当前实现已支持三类 status：

#### `succeeded`

- 使用 role-specific success contract 推进状态机

#### `blocked`

- sidecar 会对任务执行 block
- block reason 优先取：
  - `output.blocked_reason`
  - `payload.error`
  - fallback: `blocked`

#### 其他任何值

- 当前统一按失败处理
- sidecar 会对任务执行 block
- 失败原因优先取：
  - `payload.error`
  - fallback: `<role> execution failed`

### 5.6 `status=succeeded` 时的 role-specific行为

#### coordinator succeeded

sidecar 会写入：

- `goal`
- `acceptance_criteria`
- `risk_notes`
- `proposed_steps`

并推进：

- `inbox -> triaging -> queued`

最终下一个角色为：

- `executor`

#### executor succeeded

sidecar 会写入：

- `result_summary`
- `evidence`
- `open_issues`
- `followup_notes`

并推进：

- `queued|rework -> executing -> reviewing`

最终下一个角色为：

- `reviewer`

#### reviewer succeeded

sidecar 要求 `output.review_decision` 为：

- `approve`
- `reject`

并调用 review 路径推进状态机：

- `approve -> done`
- `reject -> rework`

同时写入：

- `reasons`
- `required_rework`
- `residual_risk`

### 5.7 Result 示例

```json
{
  "invoke_id": "inv:task-req-openclaw-001:coordinator:v1:a1",
  "task_id": "task-req-openclaw-001",
  "role": "coordinator",
  "trace_id": "trace-openclaw-001",
  "status": "succeeded",
  "output": {
    "goal": "明确 sidecar 与 OpenClaw 的真实接线 contract",
    "acceptance_criteria": [
      "ingress/invoke/result contract 可执行",
      "异常场景有明确语义"
    ],
    "risk_notes": [
      "不要让 callback 与 submit 状态互相覆盖"
    ],
    "proposed_steps": [
      "扩写 contract",
      "补异常矩阵测试",
      "推进 staged rollout"
    ]
  }
}
```

---

## 6. Hook Token 鉴权规则

当前 hook token 主要用于：

- `POST /hooks/openclaw/ingress`
- `POST /hooks/openclaw/result`
- HTTP runtime invoke 中注入 `callbacks.result.headers`

### 当前规则

1. 若 `hooks_token` 为空：
   - hook 入口当前不会进行 token 匹配通过校验（但真实部署不建议留空）
2. 若 `hooks_token` 非空：
   - 进入 `/hooks/openclaw/*` 的请求必须提供匹配的：
     - `X-OpenClaw-Hooks-Token`
3. hook 鉴权优先读取当前 runner 配置；若无 runner，则读取全局配置

这意味着：

- 真实部署时，`OPENCLAW_HOOKS_TOKEN` 应视为必须配置项
- 运行时 callback 合同与 hook 鉴权必须保持一致

---

## 7. 错误与异常语义

### 7.1 Runtime submission error

当前 runtime bridge 与 dispatcher 已使用结构化错误语义，常见包括：

- `configuration_error`
- `payload_error`
- `runtime_error`
- `client_error`
- `server_error`
- `timeout`
- `connection_error`
- `callback_payload_error`

这些错误会进入：

- dispatch result
- recent runtime submission summary
- remote validation blockers

### 7.2 late failure ignored

当前已实现一类关键竞态语义：

- 如果上游已经通过 callback 成功推进了任务状态
- 但 invoke 请求随后又以失败响应返回

则 dispatcher 可将其视为：

- `late_failure_ignored`

含义是：

- result truth 优先于迟到的 submit 失败
- 避免把已经推进成功的任务又错误打回 `submit_failed`

### 7.3 remote_validate blocker 分层

当前远端验证会把问题按层分类：

- `config_blockers`
- `probe_blockers`
- `dispatch_blockers`
- `result_blockers`

这四类 blocker 是当前值班与 staging 验证时的主要排障切口。

---

## 8. 当前已验证的真实 contract 事实

以下行为已被代码和测试证明：

- ingress 使用 `request_id` 幂等
- result 使用 `invoke_id` 幂等
- HTTP invoke payload 可自动注入 `callbacks.result`
- hook 入口支持 token 鉴权
- HTTP runtime 可完成最小 `invoke -> callback -> state advance` 闭环
- CLI bridge 可完成本地调用后再回调 sidecar
- reviewer-only role-specific staging 已在 AWS 上验证通过

---

## 9. 当前仍需继续补强的 contract 方向

本文档描述的是当前真实 contract，但仍有下一阶段补强空间：

1. 把 callback payload 缺字段、非法 role、invoke_id 过期等异常场景写得更细
2. 明确 ingress 来源约束与上游 trace_id 继承规范
3. 补全更多 result callback 并发/竞态测试
4. 与 staged rollout / deployment automation 文档形成更直接的相互引用

相关下一阶段计划见：

- `docs/plans/2026-03-15-real-openclaw-integration-next-plan.md`
