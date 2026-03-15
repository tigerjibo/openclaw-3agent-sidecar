# CLI Bridge Next Iteration Plan

**Goal:** 在已经验证 `openclaw-cli://main` 可真实跑通的基础上，把 `openclaw-3agent-sidecar` 的 CLI runtime bridge 从“已接通、可验证”推进到“可值班、可治理、可继续生产化”的下一迭代状态。

**Architecture:** 保持 sidecar 与官方 OpenClaw 的边界不变：官方 OpenClaw 继续负责 agent runtime，本仓库负责 task truth、3-agent 状态机、dispatch / recovery / observability。本轮不回退到 HTTP invoke 探路，也不扩写角色体系，而是在 `sidecar/adapters/openclaw_runtime.py`、`sidecar/service_runner.py`、`sidecar/remote_validate.py`、相关测试和运维文档之上继续收口 CLI bridge 的观测、超时治理、失败分类与角色解耦准备。

**Tech Stack:** Python 3.9+、SQLite、pytest、OpenClaw CLI、当前 sidecar HTTP control plane。

## 完成状态快照（2026-03-15）

本轮计划已完成并合入 `master`，核心落地点如下：

- 已完成 CLI 进程摘要输出：`exit_code`、`stdout_excerpt`、`stderr_excerpt`
- 已完成 callback failure 分类与结构化回填
- 已完成 `integration.runtime_invoke.recent_submission` 最近一次提交摘要
- 已完成独立 CLI timeout 配置与 submit retry/backoff 基础治理
- 已完成 `remote_validate` 的 blocker 分层输出
- 已完成 CLI bridge 故障 runbook
- 已完成 role-specific agent 配置项与真实按 role 路由
- 已完成发布说明模板：`docs/plans/release-note-template.md`
- 已完成 reviewer-only staging 基线固化：`deploy/aws-role-specific-agent-reviewer-only.env.example`

本轮完成后，CLI bridge 已从“可接通”推进到“可值班、可治理、可按角色分流”，后续如继续推进，建议优先转向真实环境验证、发布流程固化与更细的生产观测。

其中，当前 AWS staging 上最安全、且已被真实闭环验证的 role-specific rollout 起点为：

- `OPENCLAW_RUNTIME_INVOKE_URL=openclaw-cli://main`
- `OPENCLAW_COORDINATOR_AGENT_ID=`
- `OPENCLAW_EXECUTOR_AGENT_ID=`
- `OPENCLAW_REVIEWER_AGENT_ID=sysarch`

对应基线与操作入口：

- `deploy/aws-role-specific-agent-reviewer-only.env.example`
- `deploy/aws-role-specific-agent-staging-rollout-checklist.md`
- `docs/plans/2026-03-15-role-specific-agent-staging-validation.md`

---

## 当前基线（按代码真实状态）

在开始本轮前，应明确当前已经具备：

- `CliOpenClawRuntimeBridge` 已支持 `openclaw agent --agent <id> --json`
- sidecar 已支持 `openclaw-cli://<agent_id>` / `openclaw-agent://<agent_id>`
- 真实 AWS 上已完成一次 coordinator -> executor -> reviewer -> done 的端到端闭环
- `openclaw-sidecar-remote-validate` 已可运行 probe-only 和 `--dispatch-sample`
- CLI bridge 第一轮观测已完成：
  - bridge 元信息可见
  - probe 可区分 `configuration_error` / `runtime_error`
  - result failed 可回传结构化 `error_kind`
  - `remote_validate` 能识别 `dispatch_sample=result_failed:*`

因此，这一轮不再回答“CLI bridge 能不能用”，而要回答：

1. 出故障时是否能快速定位
2. 长时间运行时是否能稳定治理
3. 后续是否容易切到 role-specific agents

---

## 设计边界

### 这一轮要做

1. **CLI bridge 更细观测**
   - return code / stderr / stdout 摘要
   - callback 失败原因细化
   - 最近一次成功/失败的轻量状态面

2. **CLI timeout / retry 治理**
   - 独立 CLI timeout 配置
   - retryable vs non-retryable 边界收口
   - submit_failed 的后续策略更清楚

3. **角色解耦准备**
   - 为后续 `coordinator / executor / reviewer` -> 独立 OpenClaw agent 映射打基础
   - 先做配置设计和 bridge 选择逻辑，不急着一次性切换线上

4. **运维与验证文档补强**
   - remote validate 输出分层
   - 常见 CLI 故障 runbook
   - 发布说明模板

### 这一轮先不做

- 不回到 HTTP `/runtime/invoke` 方向重新打主路径
- 不改官方 OpenClaw 核心代码
- 不扩展第 4 个或更多 runtime role
- 不做重型 UI / dashboard 前端
- 不做完整通知系统

---

## Workstream 1：CLI bridge 观测增强

### Task 1：记录 CLI stderr / exit code / stdout 摘要

**Files:**

- Modify: `sidecar/adapters/openclaw_runtime.py`
- Modify: `sidecar/service_runner.py`
- Modify: `tests/test_openclaw_cli_runtime_bridge.py`
- If needed: `tests/test_service_runner_ops_summary.py`

1. 为 CLI submit 结果补充：
   - `exit_code`
   - `stderr_excerpt`
   - `stdout_excerpt`
2. 对输出做截断，避免把整段日志塞进 ops payload。
3. 区分：
   - agent 命令执行失败
   - agent 命令返回非 JSON
   - agent 返回 JSON 但 role 输出 schema 不合格
4. 保持现有 API 兼容，不破坏已有测试语义。

### Task 2：细化 callback 失败观测

**Files:**

- Modify: `sidecar/adapters/openclaw_runtime.py`
- Modify: `tests/test_openclaw_cli_runtime_bridge.py`
- Modify: `tests/test_openclaw_runtime_integration.py`

1. 把 callback 失败细分为：
   - `client_error`
   - `server_error`
   - `timeout`
   - `connection_error`
   - `callback_payload_error`（如返回体不可解析）
2. 将 callback failure 的结构化信息回填到 runtime submission response。
3. 确保 `remote_validate --dispatch-sample` 能区分：
   - CLI 已成功跑完，但 callback 失败
   - CLI 本身未跑成功

### Task 3：增加最近桥接状态摘要

**Files:**

- Modify: `sidecar/service_runner.py`
- If needed: `sidecar/runtime/dispatcher.py`
- Modify: `tests/test_service_runner_ops_summary.py`

1. 在 `integration.runtime_invoke` 下增加轻量摘要，例如：
   - `last_submit_at`
   - `last_submit_status`
   - `last_error_kind`
   - `last_error_message`
2. 首版只保留最近一次，不急着做历史窗口。
3. 让 ops/summary 能回答“最近一次 CLI bridge 到底坏在哪里”。

---

## Workstream 2：CLI timeout / retry / submit_failed 治理

### Task 4：引入独立 CLI timeout 配置

**Files:**

- Modify: `sidecar/config.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `sidecar/service_runner.py`
- Modify: `tests/test_openclaw_cli_runtime_bridge.py`

1. 增加配置项，例如：
   - `OPENCLAW_RUNTIME_CLI_TIMEOUT_SEC`
2. 让 `CliOpenClawRuntimeBridge` 使用该值，而不是只依赖内部默认值。
3. 补充配置缺省值与文档说明。

### Task 5：明确 submit_failed 后续策略

**Files:**

- Modify: `sidecar/runtime/dispatcher.py`
- Modify: `sidecar/runtime/recovery.py`
- Modify: `tests/test_dispatch_retry_strategy.py`
- If needed: `tests/test_dispatcher.py`

1. 梳理哪些错误应该：
   - 允许 retry
   - 直接 blocked
   - 保持 submit_failed 等待人工/maintenance 收口
2. 给 `submission_error_kind` 定义更清晰的恢复语义。
3. 至少补以下测试：
   - retryable timeout
   - non-retryable configuration_error
   - late failure ignored 场景

### Task 6：补最小 backoff / retry 上限

**Files:**

- Modify: `sidecar/runtime/recovery.py`
- Modify: `sidecar/service_runner.py`
- If needed: `sidecar/config.py`
- Modify: `tests/test_dispatch_retry_strategy.py`

1. 让 retryable 的 submit_failed 不至于无限打转。
2. 增加最小控制项，例如：
   - 最大重试次数
   - 基础重试间隔
3. 首版不用复杂指数退避，但要有明确上限。

---

## Workstream 3：role-specific OpenClaw agents 准备

### Task 7：设计 role -> agent 映射配置

**Files:**

- Modify: `sidecar/config.py`
- Modify: `.env.example`
- Modify: `README.md`
- If needed: `sidecar/contracts.py`
- If needed: `tests/test_openclaw_cli_runtime_bridge.py`

1. 增加配置，例如：
   - `OPENCLAW_COORDINATOR_AGENT_ID`
   - `OPENCLAW_EXECUTOR_AGENT_ID`
   - `OPENCLAW_REVIEWER_AGENT_ID`
2. 保持向后兼容：如果未配置，则继续回退到 `openclaw-cli://main`。
3. 先补配置与选择逻辑，不要求本轮一定切线上。

### Task 8：让 CLI bridge 按 role 选择 agent

**Files:**

- Modify: `sidecar/service_runner.py`
- Modify: `sidecar/adapters/openclaw_runtime.py`
- Modify: `tests/test_openclaw_cli_runtime_bridge.py`
- If needed: `tests/test_dispatcher.py`

1. 让 invoke payload 中的 role 能参与 agent 选择。
2. 保持现有单 agent 路径继续可用。
3. 至少测试：
   - coordinator 走 coordinator agent
   - reviewer 走 reviewer agent
   - 配置缺失时回退到 main

---

## Workstream 4：运维与发布收口

### Task 9：增强 remote_validate 输出分层

**Files:**

- Modify: `sidecar/remote_validate.py`
- Modify: `tests/test_remote_validate.py`
- Modify: `README.md`
- Modify: `docs/operations-runbook.md`

1. 把阻塞项分成更清晰层次：
   - config blockers
   - probe blockers
   - dispatch blockers
   - result blockers
2. 使输出更适合值班同学直接判读。
3. 保持命令返回码语义稳定。

### Task 10：补 CLI bridge 常见故障 runbook

**Files:**

- Modify: `docs/operations-runbook.md`
- If needed: `deploy/README.md`

1. 新增常见故障条目：
   - CLI not found
   - callback 401
   - callback timeout
   - malformed role output
   - runtime stderr 非空/exit code 非零
2. 给出最小排障顺序。

### Task 11：补发布说明模板

**Files:**

- Create: `docs/plans/release-note-template.md`
- If needed: `README.md`

1. 固化发布说明结构：
   - 本次变更
   - 风险点
   - 验证结果
   - 回滚方式
2. 让后续上线不靠临时手写口径。

---

## 推荐实现顺序

建议按这个顺序推进：

1. **Task 1：stderr / exit code / stdout 摘要**
2. **Task 2：callback failure 分类**
3. **Task 3：最近桥接状态摘要**
4. **Task 4：独立 CLI timeout 配置**
5. **Task 5：submit_failed 策略收口**
6. **Task 6：最小 backoff / retry 上限**
7. **Task 9：remote_validate 输出分层**
8. **Task 10：CLI 故障 runbook**
9. **Task 7：role -> agent 配置设计**
10. **Task 8：role-specific agent 路由**
11. **Task 11：发布说明模板**

这样能优先解决：

- 线上排障信息不足
- submit_failed 治理边界模糊
- 后续多角色 agent 切换没有配置基础

---

## 本周建议落地范围

如果只做一个 1 周迭代，建议锁定：

### Sprint Slice A（推荐）

- Task 1
- Task 2
- Task 3
- Task 4
- Task 9
- Task 10

这组组合的特点是：

- 风险低
- 不破坏主链路
- 运维价值高
- 能立刻提升值班体验

---

## 验收标准

这一轮完成后，应满足：

1. CLI bridge 失败时，ops/summary 能看到结构化失败信息
2. `remote_validate --dispatch-sample` 能区分 submit 成功但 result 失败 / callback 失败 / CLI 本体失败
3. CLI timeout 具备独立配置项
4. submit_failed 至少具备清晰的 retryable / non-retryable 语义
5. 运维文档能指导常见 CLI bridge 故障排查
6. 为 role-specific agent 切换预留好配置和测试方向
7. 以下验证稳定通过：
   - `pytest tests -q`
   - `python -m compileall sidecar`

---

## 建议接手提示

> 下一阶段不要再重复证明 CLI bridge 能跑，而应围绕“失败是否可解释、运行是否可治理、后续是否容易做角色解耦”推进。优先把 CLI bridge 的 stderr/exit code/callback failure 收口，再做 timeout/retry 策略，最后推进 role-specific OpenClaw agents。
