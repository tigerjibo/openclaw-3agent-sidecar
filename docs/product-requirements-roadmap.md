# OpenClaw 3-Agent Sidecar 需求 / 方案 / 规划

## 1. 原始目标

本项目的目标不是再做一个“会聊天的 agent 包装层”，而是构建一套基于官方 OpenClaw 底座的 **制度化任务编排系统**。

它要解决的问题包括：

- 任务能否被拆成明确阶段，而不是一轮对话结束就丢失上下文
- 任务能否由不同角色分工推进，而不是由单个 agent 自我裁判
- 任务能否在异常、阻塞、重启后继续恢复，而不是永久悬挂
- 任务结果能否有审计链路，而不是只留下零散聊天记录

对外品牌层可采用 **“明制小内阁”** 的母题来降低理解门槛：

- 皇帝：用户 / 任务发起者
- 首辅：统筹与拆解，对应 `coordinator`
- 大学士：承办与执行，对应 `executor`
- 监审官：独立审议与封驳，对应 `reviewer`

但产品与实现必须始终遵循：**外宣人格化命名不替代 runtime 内部角色抽象**。

## 2. 当前产品边界

### 本仓库负责

- 任务内核（tasks / task_events）
- 状态机与角色边界
- adapter 契约与回写逻辑
- dispatcher / scheduler / recovery / health
- 可观测与投影视图

### 本仓库不负责

- 官方 OpenClaw gateway 核心代码修改
- 官方 OpenClaw session 主逻辑改造
- 重型前端系统
- 与 sidecar 无关的旧仓业务功能继续叠加

## 3. 当前已完成能力

### P0 已完成

#### 任务内核

- `storage.py`
- `models.py`
- `events.py`
- `state_machine.py`
- `api.py`

#### 最小 adapter

- `sidecar/adapters/ingress.py`
- `sidecar/adapters/agent_invoke.py`
- `sidecar/adapters/result.py`

#### 最小 runtime

- `sidecar/runtime/dispatcher.py`
- `sidecar/runtime/scheduler.py`
- `sidecar/runtime/recovery.py`
- `sidecar/runtime/agent_health.py`
- `sidecar/service_runner.py` 健康面已接入角色级 health snapshot

#### 最小测试闭环

- ingress 测试
- invoke payload 测试
- result 回写测试
- end-to-end minimal loop 测试
- dispatcher / scheduler 测试

## 4. 当前仍未完成能力

### P0 仍待补齐

1. `service_runner.py` 持久化改造
   - 从 `:memory:` 过渡到真实 DB 路径
   - 保障重启后状态可恢复

2. runtime 自动驱动补齐
   - scheduler / service runner 定期调用 recovery
   - health / readiness / metrics 联动更完整
   - 为 restart / stale / blocked 场景补更强测试

### P1 待完成

1. 与真实 OpenClaw runtime 的接线
   - 真实 ingress 来源对接
   - 真正的 agent invoke 路由
   - result 回写链路落地

2. 业务入口闭环
   - Feishu / 指定制度化入口
   - 回传格式与人工动作入口

### P2 待完成

1. 生产化与运维
   - 部署脚手架
   - 配置管理
   - 指标与异常面板
   - 运行 SOP

## 5. 方案概述

### 方案核心

采用：

- **官方 OpenClaw 作为底座**
- **openclaw-3agent-sidecar 作为独立 orchestration layer**

### 关键原则

1. **不改官方核心源码**
2. **任务状态真相源只在 sidecar**
3. **所有关键步骤必须可审计**
4. **普通聊天与制度化任务必须分流**
5. **角色边界必须严格，禁止 executor 自我审批**
6. **对外可用“明制小内阁”叙事，对内坚持 `coordinator / executor / reviewer` 角色名**

## 6. 推荐技术路线

### 阶段一：巩固最小内核闭环

目标：把当前最小实现变成“可持续跑的最小系统”。

建议动作：

- 改造 `service_runner.py` 使用持久化 DB
- 让 scheduler / service runner 周期性驱动 recovery / health
- 为 runtime 补充更多异常/重启/停滞测试

### 阶段二：对接真实 OpenClaw

目标：让 sidecar 不仅能本地演示闭环，还能真的挂到官方 OpenClaw 上跑。

建议动作：

- 对接真实 ingress 源
- 对接真实 agent invoke
- 让 result 从真实调用返回而不是测试模拟

### 阶段三：业务闭环与运维

目标：让 sidecar 成为真正可上线、可排障、可交接的系统。

建议动作：

- 对接业务入口
- 补 metrics / alert / role health
- 完成部署脚手架与运行文档

当前已落地的阶段三基础包括：

- integration probe 的结构化观测
- gateway hook 自动注册与 maintenance 重试
- hook 注册失败次数阈值触发的 health / readiness 联动
- 初版 `docs/operations-runbook.md`

## 7. 优先级路线图

### P0（建议立即做）

- persistent DB runner
- recovery / health 自动调度接线
- runtime 相关测试补强

### P1（P0 稳住后做）

- 真实 OpenClaw 接线
- Feishu / 制度化入口联通
- 人工动作权限与回传

### P2（上线前逐步补齐）

- 生产化部署
- 运维 SOP
- 监控与异常大盘
- 回滚与应急策略

## 8. 当前推荐开发顺序

如果从现在开始，在新仓继续开发，推荐按下面顺序推进：

1. `sidecar/service_runner.py` 持久化数据库路径
2. scheduler / service runner 接入 recovery / health 的周期性驱动
3. `tests/` 中新增 restart / stale / blocked / timeout 回归测试
4. `sidecar/adapters/` 与真实 OpenClaw 的对接层
5. 文档与部署说明同步完善
6. 轻量活动流 / 演示面增强

## 9. 不建议做的事情

以下方向当前不建议继续：

- 回到旧仓 `M:\code\openclaw` 里继续实现 sidecar 主功能
- 直接改官方 OpenClaw 核心逻辑来塞进 3-agent 状态机
- 在 recovery / health 还没落地前过早做重型 UI
- 把 sidecar 重新做成一个依赖旧仓目录结构的半独立模块

## 10. 当前阶段结论

> 当前 `openclaw-3agent-sidecar` 已经完成了“独立仓初始化 + task kernel + adapter 最小闭环 + recovery / health 在内的 runtime 基础闭环”，下一阶段的核心任务不是重写角色故事，而是把持久化、自动恢复调度和真实 OpenClaw 接线做实，同时在对外层使用“明制小内阁”统一传播口径。

补充说明：当前仓库也已经具备第一批面向真实上游接线的运维语义，包括 hook registration 状态、自动重试窗口、连续失败阈值告警，以及 readiness 阻断能力。
