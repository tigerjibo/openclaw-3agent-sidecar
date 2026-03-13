# New AI Agent Handoff

## 你当前所在的正确工作仓库

从现在开始，`3-agent sidecar` 的后续实现应在：

- `D:\code\openclaw-3agent-sidecar`

继续进行。

**不要** 在旧仓库：

- `M:\code\openclaw`

里继续实现 sidecar 主功能。

旧仓目前主要承担的是：

- 历史设计文档来源
- 迁移参考
- 官方 OpenClaw 相关上下文参考

而不是新的 sidecar 主开发仓。

## 你接手的项目是什么

这是一个独立于官方 OpenClaw 源码之外的 3-agent orchestration sidecar。

### 它不是

- 不是官方 OpenClaw fork 的继续改造项目
- 不是要修改官方 OpenClaw 核心代码的项目
- 不是单 agent 聊天代理包装层

### 它是

- 基于官方 OpenClaw runtime 的 sidecar 编排层
- 负责制度化任务状态机与角色分工
- 负责 dispatch / scheduler / recovery / health / audit

### 对外宣传口径（新增）

这个项目在对外介绍时，可以采用 **“明制小内阁”** 的表达：

- 皇帝：用户 / 下发任务者
- 首辅：对应 `coordinator`
- 大学士：对应 `executor`
- 监审官：对应 `reviewer`

但在代码、测试、API、数据库与状态机里，仍必须坚持使用：

- `coordinator`
- `executor`
- `reviewer`

## 三角色定义

- `coordinator`
  - 归纳任务目标
  - 形成 acceptance criteria
  - 输出 brief
- `executor`
  - 负责执行任务
  - 回填 result summary / evidence / open issues
- `reviewer`
  - 独立审核
  - 决定 approve / reject

## 当前代码状态（已完成）

### 核心内核

- `sidecar/storage.py`
- `sidecar/models.py`
- `sidecar/events.py`
- `sidecar/state_machine.py`
- `sidecar/api.py`

### 适配层

- `sidecar/adapters/ingress.py`
- `sidecar/adapters/agent_invoke.py`
- `sidecar/adapters/result.py`

### 运行时最小闭环

- `sidecar/runtime/dispatcher.py`
- `sidecar/runtime/scheduler.py`
- `sidecar/runtime/recovery.py`
- `sidecar/runtime/agent_health.py`
- `sidecar/service_runner.py` 健康面已接入角色级 health snapshot

### 角色文件

- `sidecar/roles/shared/AGENTS.md`
- `sidecar/roles/coordinator/SOUL.md`
- `sidecar/roles/executor/SOUL.md`
- `sidecar/roles/reviewer/SOUL.md`

## 当前仍未完成

高优先级未完成项：

1. `sidecar/service_runner.py` 使用持久化 DB 路径
2. scheduler / service runner 周期性驱动 recovery / health
3. 与真实 OpenClaw runtime 的真实接线

## 你应该先读哪些文件

建议接手后按这个顺序读：

1. `README.md`
2. `docs/project-introduction.md`
3. `docs/product-requirements-roadmap.md`
4. `docs/architecture.md`
5. `docs/migration-notes.md`
6. `docs/adapter-contract.md`
7. `sidecar/` 下当前实现
8. `tests/` 下现有测试

## 当前已验证状态

最近一次验证已通过：

- `pytest tests -q`
- `python -m compileall sidecar`

结果为：

- `PYTEST_EXIT=0`
- `COMPILE_EXIT=0`

因此接手时不要把项目当成“纯文档仓”；它已经有最小可运行闭环。

## 你接下来应该优先做什么

推荐顺序：

1. 改造 `service_runner.py` 使用持久化 DB
2. 为 recovery / restart / stale / timeout 场景补更强测试
3. 让 scheduler / service runner 自动驱动 recovery / health
4. 再开始对接真实 OpenClaw runtime

## 重要开发约束

### 约束 1：不要回到旧仓继续实现 sidecar

sidecar 的主实现今后以新仓为准。

### 约束 2：不要改官方 OpenClaw 核心源码

如果要与 OpenClaw 交互，应优先通过：

- ingress adapter
- invoke adapter
- result adapter
- 官方支持的 webhook / routing / workspace / skills 机制

### 约束 3：任务真相源只在 sidecar

不要把 OpenClaw session 误当作任务状态真相源。

### 约束 4：继续遵守 TDD + fresh verification

每轮新增行为建议先写失败测试，再补实现。
完成后至少运行：

- `pytest tests -q`
- `python -m compileall sidecar`

## 推荐的下一句开工提示词

如果你是一个新 AI agent，接手后可以从下面这句开始：

> 请在 `D:\code\openclaw-3agent-sidecar` 中继续开发，不要修改 `M:\code\openclaw` 里的 sidecar 逻辑。先阅读 `README.md`、`docs/project-introduction.md`、`docs/product-requirements-roadmap.md`、`docs/architecture.md`、`docs/migration-notes.md`，然后以 TDD 方式优先实现 `sidecar/runtime/recovery.py`，补相应测试，并在完成后运行 `pytest tests -q` 与 `python -m compileall sidecar` 验证。
> 请在 `D:\code\openclaw-3agent-sidecar` 中继续开发，不要修改 `M:\code\openclaw` 里的 sidecar 逻辑。先阅读 `README.md`、`docs/project-introduction.md`、`docs/product-requirements-roadmap.md`、`docs/architecture.md`、`docs/migration-notes.md`，理解该项目对外可使用“明制小内阁”叙事、对内仍坚持 `coordinator / executor / reviewer`，然后以 TDD 方式优先推进 `sidecar/service_runner.py` 的持久化 DB 路径与后续 recovery / health 自动驱动。
