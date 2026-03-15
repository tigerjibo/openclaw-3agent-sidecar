# CLI Bridge Next Iteration Release Note

> 发布日期：2026-03-15
>
> 适用范围：`openclaw-3agent-sidecar` CLI runtime bridge 本轮治理与角色解耦迭代。

---

## 1. 发布概览

- **发布名称 / 批次：** CLI bridge next iteration
- **发布日期：** 2026-03-15
- **发布负责人：** GitHub Copilot / tigerjibo 协作落地
- **变更分支 / 提交范围：** `master`
- **目标环境：**
  - [x] local
  - [ ] staging
  - [ ] production
- **发布类型：**
  - [x] feature
  - [x] fix
  - [x] docs / runbook
  - [x] operational change
  - [ ] rollback

### 一句话摘要

> 本次发布把 sidecar 的 CLI runtime bridge 从“能接通”推进到“更可值班、可治理、可按角色分流”，并补齐了后续上线所需的发布说明模板。

---

## 2. 本次变更

### 变更目标

- 解决 CLI bridge 在可观测性、失败分类、timeout/retry 治理和 role-specific agent 演进上的缺口。
- 对应计划：`docs/plans/2026-03-15-cli-bridge-next-iteration-plan.md`
- 是否涉及上游 OpenClaw 接线：
  - [x] 是
  - [ ] 否

### 代码与配置改动

#### 代码改动

- `sidecar/adapters/openclaw_runtime.py`
  - 增加 CLI 进程摘要（`exit_code`、`stdout_excerpt`、`stderr_excerpt`）
  - 细分 callback failure 类型
  - 支持按 sidecar role 选择独立 OpenClaw agent
  - 在 runtime submission response 中返回 `selected_agent_id`
- `sidecar/service_runner.py`
  - 集成 CLI timeout、role-agent mapping 和 bridge metadata
  - 让 ops/integration summary 可见最近 runtime submission 摘要
- `sidecar/runtime/dispatcher.py`
  - 记录最近一次 runtime submission 的状态、错误类型、恢复动作
- `sidecar/runtime/recovery.py`
  - 增加 submit_failed 的 retry delay 与 max attempts 治理
- `sidecar/remote_validate.py`
  - 输出分层 blocker：`config_blockers`、`probe_blockers`、`dispatch_blockers`、`result_blockers`

#### 配置改动

- 新增 / 使用以下环境变量：
  - `OPENCLAW_RUNTIME_CLI_TIMEOUT_SEC`
  - `OPENCLAW_RUNTIME_SUBMIT_RETRY_DELAY_SEC`
  - `OPENCLAW_RUNTIME_SUBMIT_MAX_ATTEMPTS`
  - `OPENCLAW_COORDINATOR_AGENT_ID`
  - `OPENCLAW_EXECUTOR_AGENT_ID`
  - `OPENCLAW_REVIEWER_AGENT_ID`
- 兼容行为保持不变：若 role-specific agent 未配置，仍回退到 `OPENCLAW_RUNTIME_INVOKE_URL` 中的默认 agent，例如 `openclaw-cli://main`

#### 文档改动

- `docs/operations-runbook.md`
  - 增补 CLI bridge 常见故障排查
- `docs/plans/release-note-template.md`
  - 固化发布说明模板
- `README.md`
  - 更新配置项与模板入口

#### 数据库 / 持久化改动

- [x] 无
- [ ] 有，说明如下：

### 对外行为变化

- **新增行为：**
  - CLI bridge 可按 `coordinator / executor / reviewer` 选择不同 agent
  - ops summary 可看到最近一次 runtime submission 摘要
  - remote validate 可按层次输出 blocker
- **保持兼容的旧行为：**
  - 单 agent 路径 `openclaw-cli://main` 继续可用
  - 未配置 role-specific agent 时不改变既有执行路径
- **已知未覆盖范围：**
  - 本轮未执行新的 AWS staging / production 远端验证
  - 本轮未改官方 OpenClaw runtime 本体

---

## 3. 风险点

### 技术风险

- [x] runtime bridge 路由变化
- [ ] gateway hook 注册变化
- [x] result callback 鉴权变化
- [x] recovery / retry 行为变化
- [ ] SQLite / 持久化风险
- [ ] 仅文档风险

### 风险说明

- **最高风险点：** role-specific agent 路由配置错误，导致某个角色走到不存在或错误的上游 agent。
- **触发条件：** `OPENCLAW_COORDINATOR_AGENT_ID` / `OPENCLAW_EXECUTOR_AGENT_ID` / `OPENCLAW_REVIEWER_AGENT_ID` 配置失真，或上游 agent 不可用。
- **用户可见症状：** 某个角色持续 `submit_failed`、`blocked`，或 `remote_validate --dispatch-sample` 出现 callback / result failure。
- **值班观察点：**
  - `GET /healthz`
  - `GET /readyz`
  - `GET /ops/summary`
  - `openclaw-sidecar-remote-validate`

### 缓释措施

- 所有 role-specific agent 配置保留默认 fallback 到 `main`
- 已补充定向测试与全量测试，并将 release / rollback 检查项固定为模板

---

## 4. 验证结果

### 本地 / CI 验证

- [x] `pytest tests -q`
- [x] `python -m compileall sidecar`

#### 关键定向测试

- `pytest tests/test_config.py tests/test_openclaw_cli_runtime_bridge.py -q`
- `pytest tests/test_openclaw_cli_runtime_bridge.py tests/test_dispatcher.py tests/test_service_runner_ops_summary.py -q`

### 环境验证

- [x] 未做环境验证
- [ ] 已做 staging 验证
- [ ] 已做 production 验证

### 验证记录

#### 命令 / 检查项

- `pytest tests/test_config.py tests/test_openclaw_cli_runtime_bridge.py -q`
- `pytest tests/test_openclaw_cli_runtime_bridge.py tests/test_dispatcher.py tests/test_service_runner_ops_summary.py -q`
- `pytest tests -q`
- `python -m compileall sidecar`

#### 结果摘要

- Task 7 定向测试：`16 passed`
- Task 8 定向测试：`35 passed`
- 全量测试：`147 passed`
- 编译检查：通过

#### 关键观测

- `integration.status = local_only / runtime_invoke_ready`（取决于实际环境配置）
- `integration.runtime_invoke.bridge = 可展示 role_agent_mapping 与 timeout 配置`
- `integration.runtime_invoke.recent_submission = 可展示 last_submit_status / last_error_kind / last_recovery_action`
- `integration.probe = 可区分 reachable / degraded / unreachable / not_configured`

### 结论

- [x] 可发布
- [x] 可灰度
- [ ] 需人工盯盘
- [ ] 暂不建议发布

---

## 5. 发布步骤

1. 确认目标环境的 `OPENCLAW_*` 配置完整。
2. 若启用 role-specific agent，确认三个 agent id 与上游真实可用 agent 对齐。
3. 部署目标提交并重启 sidecar 服务。
4. 检查 `/healthz`、`/readyz`、`/ops/summary`。
5. 运行 `openclaw-sidecar-remote-validate`。
6. 若需要真实闭环验证，再运行 `openclaw-sidecar-remote-validate --dispatch-sample`。
7. 观察 `integration.runtime_invoke.recent_submission` 与 `integration.probe.runtime_invoke`，确认未出现新的角色路由异常。

---

## 6. 回滚方式

### 回滚触发条件

- role-specific agent 路由导致某一角色持续提交失败
- callback / result 闭环在新配置下连续失败，且 fallback 无法快速恢复

### 回滚步骤

1. 切回上一稳定提交：`189190f` 之前的稳定版本，或直接回退到不含 Task 8 的版本。
2. 清空 `OPENCLAW_COORDINATOR_AGENT_ID` / `OPENCLAW_EXECUTOR_AGENT_ID` / `OPENCLAW_REVIEWER_AGENT_ID`，恢复单 agent 路径。
3. 重启 sidecar 服务。
4. 再次检查：
   - `GET /healthz`
   - `GET /readyz`
   - `GET /ops/summary`
5. 如涉及真实接线，再运行：
   - `openclaw-sidecar-remote-validate`

### 回滚后确认项

- `integration.status` 恢复预期
- `hook_registration.status` 仍正常
- `runtime_invoke.recent_submission` 不再出现本次新增路由故障
- 如有 `blocked` 任务，确认是否需要人工解阻

---

## 7. 值班备注

### 上线后重点盯盘时间窗

- **开始时间：** 发布后首个 30~60 分钟
- **结束时间：** 首轮真实 dispatch sample 完成后
- **责任人：** 当前值班 / 发布负责人

### 重点关注指标 / 字段

- `health.status`
- `readiness.status`
- `integration.gateway.hook_registration.status`
- `integration.runtime_invoke.result_callback_ready`
- `integration.runtime_invoke.recent_submission.last_submit_status`
- `integration.runtime_invoke.recent_submission.last_error_kind`
- `integration.runtime_invoke.recent_submission.last_recovery_action`

### 若出问题先看哪里

1. `blocking_issue_groups`
2. `ops.summary.integration.runtime_invoke.recent_submission`
3. `integration.probe.runtime_invoke`
4. sidecar / upstream runtime 日志

---

## 8. 对外沟通口径（可选）

### 面向内部开发 / 值班

> 本次迭代已经完成 CLI bridge 的治理增强、角色分流能力和发版模板补齐；若上线后出现异常，请优先依据 `ops/summary` 与 `remote_validate` 的结构化输出定位，不要直接跳到原始日志层。

### 面向业务 / 非技术干系人

> 本次更新提升了 sidecar 与上游 runtime 的稳定性、可解释性与后续扩展能力，并保留了单 agent 回退路径，以降低新能力上线风险。
