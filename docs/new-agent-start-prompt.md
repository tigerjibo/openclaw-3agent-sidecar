# New Agent Start Prompt

## 用途

这份文档提供一段可以直接复制给新 AI agent 的启动提示词，用于在 `D:\code\openclaw-3agent-sidecar` 新仓中继续开发，而不再回旧仓实现 sidecar 主逻辑。

## 推荐启动提示词（完整版）

请在 `D:\code\openclaw-3agent-sidecar` 中继续开发 `openclaw-3agent-sidecar`，不要修改 `M:\code\openclaw` 里的 sidecar 主实现。这个新仓是 3-agent sidecar 的主开发仓，旧仓现在只作为历史迁移来源、参考文档来源和官方 OpenClaw 上下文参考。

在开始实现前，请先阅读以下文件，并以它们为当前真实上下文：

1. `README.md`
2. `AGENTS.md`
3. `docs/project-introduction.md`
4. `docs/product-requirements-roadmap.md`
5. `docs/architecture.md`
6. `docs/migration-notes.md`
7. `docs/adapter-contract.md`
8. `docs/ai-agent-handoff.md`
9. `docs/plans/2026-03-13-recovery-implementation-plan.md`（用于理解 recovery 设计背景，不代表当前优先级仍是 recovery）

请基于当前代码状态继续推进，不要重复做已经完成的 adapter/runtime 最小闭环。当前已经完成的能力包括：

- task kernel
- ingress / invoke / result adapters
- dispatcher / scheduler 最小运行时闭环
- recovery 首版
- agent health 首版
- service health 接入 role health snapshot
- 本地 HTTP service foundation
- adapter/runtime 基础测试

请额外注意一条对外 / 对内分层原则：

- 对外宣传层可使用“明制小内阁”表达：首辅 / 大学士 / 监审官
- 对内实现层仍必须坚持 `coordinator / executor / reviewer`
- 不要让宣传层命名反向污染代码、测试、API、数据库字段

当前优先级最高的任务是：

- 以 TDD 方式推进 `sidecar/service_runner.py` 的持久化 DB 路径

请按下面顺序执行：

1. 先阅读 `README.md`、`docs/project-introduction.md`、`docs/product-requirements-roadmap.md`、`docs/architecture.md`
2. 确认当前已完成 `recovery.py`、`agent_health.py`，不要重复实现
3. 先为 `service_runner.py` 的持久化 DB 路径补失败测试
4. 再做最小实现，优先保证：
   - 可配置 DB 路径，不再固定 `:memory:`
   - 重启后任务状态可恢复
   - 不破坏现有 `healthz` / `readyz` / runtime 测试
5. 如果本轮涉及 recovery / health 调度接线，也必须先写失败测试再补实现
6. 保持任务状态真相源只在 sidecar，不要把 OpenClaw session 当作任务状态真相源
7. 不要修改官方 OpenClaw 核心源码
8. 只在新仓里实施 sidecar 逻辑

实现过程中请遵守以下约束：

- 优先最小实现，不要过早做复杂恢复编排
- 已有 recovery 首版以“识别异常任务 + 释放错误 in-flight 状态 + 写恢复/升级事件”为主，本轮不要重复发明新语义
- 不要伪造 done，不要绕过状态机
- blocked 场景首版只做 escalation / event 收口，不强行自动解阻塞
- 每新增行为先写失败测试，再补实现

在完成本轮修改后，请至少运行以下验证：

- `pytest tests -q`
- `python -m compileall sidecar`

完成后请汇报：

1. 修改了哪些文件
2. 本轮持久化或调度接线覆盖了哪些场景
3. 哪些测试新增并通过
4. 还有哪些未完成风险

## 推荐启动提示词（精简版）

请在 `D:\code\openclaw-3agent-sidecar` 中继续开发，不要修改 `M:\code\openclaw` 里的 sidecar 逻辑。先阅读 `README.md`、`AGENTS.md`、`docs/project-introduction.md`、`docs/product-requirements-roadmap.md`、`docs/architecture.md`、`docs/migration-notes.md`、`docs/ai-agent-handoff.md`，理解该项目对外可使用“明制小内阁”叙事、对内仍坚持 `coordinator / executor / reviewer`，然后以 TDD 方式优先推进 `sidecar/service_runner.py` 的持久化 DB 路径，完成后运行 `pytest tests -q` 与 `python -m compileall sidecar` 验证。

## 使用建议

- 如果是全新 agent，优先使用“完整版”提示词。
- 如果是你已经口头解释过上下文的 agent，可使用“精简版”。
- 如果后续优先级变化了，可以只替换“当前优先级最高的任务”那一段，不必重写整份文档。
