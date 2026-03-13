# Next Phase Implementation Plan

**Goal:** 在当前已完成的 task kernel、最小 runtime 闭环、integration probe、hook auto-registration 与运维语义基础上，把 `openclaw-3agent-sidecar` 从“可验证的侧车内核”推进到“可真实接线、可稳定运行、可继续上线准备”的下一阶段。

**Architecture:** 保持“官方 OpenClaw 负责 gateway / routing / runtime，sidecar 负责 task truth / state machine / recovery / observability”的边界不变。下一阶段不重写现有 runtime，而是在 `service_runner`、`adapters/openclaw_runtime.py`、`http_service.py` 和部署/运维文档之上继续收口，优先补强真实接线、状态持久化后的恢复一致性，以及生产化运行约束。

**Tech Stack:** Python 3.9+、SQLite、pytest、本地 HTTP 控制面、官方 OpenClaw 上游 HTTP 接口。

---

## 当前基线（按代码真实状态）

在开始下一阶段前，应明确当前“已经有”的能力：

- `ServiceRunner` 已支持 `db_path` 持久化路径，并已有重启后状态保留测试
- maintenance loop / recovery / scheduler / health 已接入 runner
- 已有 OpenClaw gateway client 与 runtime bridge skeleton
- 已暴露 `/runtime/*` 与 `/hooks/openclaw/*` 接口
- 已有 integration probe、hook 注册重试、health/readiness 联动
- 已有 `deploy/` 样例脚手架与 `docs/operations-runbook.md`

因此，下一阶段**不应再把“持久化 DB 支持”当成从零开始的任务**，而应把重点放在：

1. 持久化后的恢复一致性与运行收口
2. 真实 OpenClaw 接线闭环
3. 部署与运维硬化

---

## 设计边界

### 下一阶段要做

1. **持久化并发防御与运行收口**
   - 验证重启后 maintenance / recovery / dispatch 的一致性
   - 落实 SQLite 的并发安全模式（WAL）与任务数据 TTL 自动清理，防止 DB 膨胀拖垮性能
   - 补充真实 restart / stale / blocked / timeout 回归覆盖

2. **真实 OpenClaw 接线闭环与链路追踪**
   - 让 runtime bridge / gateway hooks 从 skeleton 走向实际可配置接线
   - 固化 Trace ID 的贯穿机制（ingress -> invoke -> hook），使得 Sidecar 与 OpenClaw 间不再是可观测性黑洞
   - 定义人工干预（HITL）API Contract（如 `/runtime/unblock`），以解除 blocked 异常
   - 为 Result Hook 回写引入基于版本号的“乐观锁”，彻底切断网络重试引起的乱序流转与并发脏写

3. **生产化运行硬化**
   - 收口配置、日志、启动方式、部署说明
   - 增加 smoke check / operator checklist
   - 把“样例部署”推进到“可实际试运行”的程度

### 下一阶段先不做

- 不回到旧仓修改 OpenClaw 核心源码
- 不上重型前端或复杂控制台
- 不引入多角色扩编或新的 runtime 角色体系
- 不在 sidecar 中复制官方 OpenClaw 的 session/gateway 责任

---

## 工作流分解

## Workstream 1：持久化后的 runtime 一致性补强

### Task 1：补齐 restart consistency 测试矩阵

**Files:**
- Modify: `tests/test_service_runner_persistence.py`
- Modify: `tests/test_service_runner_runtime_loop.py`
- Modify: `tests/test_service_runner_health.py`
- If needed: `tests/test_recovery.py`

1. 为以下场景补测试：
   - runner 重启后，`dispatch_status=running` 的任务能被 recovery 正确收口
   - timeout 任务在重启前后不会重复升级或漏升级
   - blocked 任务在重启后仍能被 maintenance 识别
   - readiness/health 在重启后不会因纯内存态丢失而产生假阳性
2. 先让测试表达真实期望，再校准现有实现。
3. 跑针对性测试与全量验证。

### Task 2：明确运行态持久化边界

**Files:**
- Modify: `sidecar/service_runner.py`
- If needed: `sidecar/storage.py`
- If needed: `sidecar/models.py`
- If needed: `docs/architecture.md`

1. 梳理当前仅存在内存中的运行态：
   - maintenance history
   - integration probe cache
   - hook registration state
2. 判断哪些必须跨重启持久化，哪些只需“重启后可重建”。
3. 若选择不持久化，也要在代码和文档里明确恢复策略，避免后续误判。

### Task 3：补 runner shutdown/startup 收口语义

**Files:**
- Modify: `sidecar/service_runner.py`
- Modify: `tests/test_service_runner_cli.py`
- If needed: `tests/test_service_runner_runtime_loop.py`

1. 明确 stop/start 期间 maintenance thread、HTTP service、DB 连接的先后顺序。
2. 补“重复 start/stop、异常 stop、主线程/非主线程”相关测试。
3. 保证 runner 生命周期行为稳定可预测。

### Task 4：落实 SQLite 并发安全与数据 TTL

**Files:**
- Modify: `sidecar/storage.py`
- Modify: `sidecar/service_runner.py`
- If needed: `tests/test_service_runner_persistence.py`

1. **写写并防锁**：修改 `init_db` 与连接池逻辑，强制开启 `PRAGMA journal_mode=WAL` 与线程安全访问机制，防止死锁（database is locked）。
2. **容量防爆**：在 `run_maintenance_cycle` 中引入归档清理动作（例如清理超 30 天的已完结任务与事件归档）。
3. 编写并发执行与 TTL 归档的验证单测。

---

## Workstream 2：真实 OpenClaw 接线落地与并发防御

### Task 5：固化 sidecar 与 OpenClaw 的 contract（含 Trace ID / HITL）

**Files:**
- Modify: `docs/adapter-contract.md`
- Modify: `docs/architecture.md`
- If needed: `sidecar/contracts.py`

1. 明确三类 contract：
   - ingress payload
   - runtime invoke payload
   - result callback payload
2. 标明必填字段、鉴权头、错误码语义，以及**必须包含的系统级 `trace_id` 用于全链路追踪隔离。**
3. 补充定义 **人工干预 (Human-In-The-Loop) /runtime/intervention (或 unblock) 的 API Contract**，允许在 `blocked` 状态下通过补充信息强制恢复执行。

### Task 5：增强 gateway/runtime 适配层错误处理

**Files:**
- Modify: `sidecar/adapters/openclaw_runtime.py`
- Modify: `tests/test_openclaw_runtime_integration.py`

1. 为 gateway/runtime client 增补以下行为：
   - 非 JSON 响应的容错
   - 超时与连接错误分类
   - 明确 response payload 解析失败时的错误语义
   - 更细的 HTTP 4xx/5xx 区分
2. 为探测与真实调用复用稳定的错误分类结构。
3. 保持现有 probe/ops summary 的兼容性。

### Task 7：打通真实 invoke/result 最小闭环

**Files:**
- Modify: `sidecar/runtime/dispatcher.py`
- Modify: `sidecar/http_service.py`
- Modify: `sidecar/service_runner.py`
- Modify: `tests/test_dispatcher.py`
- Modify: `tests/test_openclaw_runtime_integration.py`
- If needed: `tests/test_end_to_end_minimal_loop.py`

1. 让 dispatcher 对外部 runtime submission 失败时给出稳定可恢复语义。
2. 明确 sidecar 在以下场景的策略与演练：
   - invoke 被拒绝
   - reviewer 结果晚到/重复到达
3. 至少做出“单 task 在真实 HTTP 接线下能完成一次 coordinator -> executor -> reviewer”的最小闭环验证模型。

### Task 8：为 Result Hook 引入乐观锁并发防御

**Files:**
- Modify: `sidecar/storage.py` 或 `sidecar/models.py`
- Modify: `sidecar/adapters/result.py`
- Create/Modify: `tests/test_result_optimistic_locking.py`

1. **状态机代数号**：在 `tasks` 表级别引入 `task_version` 字段，并在分发时 (Dispatch) 更新它。
2. **防脑裂拦截**：`Result hook` 回写时，必须执行类似 `UPDATE tasks ... WHERE task_id = ? AND task_version = ?` 的前置校验。
3. 如果 `version` 匹配失败，即认为属于“网络重发导致的历史脏单”或“上游同一时刻发多次”，直接短路防御并记录幂等，避免状态机走入死胡同。

---

## Workstream 3：部署与运维硬化

### Task 9：把部署样例升级为试运行手册

**Files:**
- Modify: `deploy/README.md`
- Modify: `docs/operations-runbook.md`
- If needed: `README.md`
- If needed: `.env.example`

1. 把样例部署说明补成可执行 checklist：
   - 环境变量
   - 启动命令
   - 健康检查
   - 常见失败排查
2. 明确 Linux/Windows 最小落地路径。
3. 补一段“本地试运行 smoke 流程”。

### Task 10：补 smoke 验证脚本或测试入口

**Files:**
- If needed: `tests/test_service_runner_cli.py`
- If needed: `deploy/README.md`
- If needed: `README.md`

1. 约定一个最小 smoke 流程，用于验证：
   - runner 可启动
   - `/healthz` / `/readyz` / `/ops/summary` 可访问
   - 若配置上游地址，integration probe 能返回预期状态
2. 优先用现有 pytest 或最小脚本表达，不急着引入新工具链。

### Task 11：补配置与日志约束

**Files:**
- Modify: `sidecar/config.py`
- Modify: `sidecar/__main__.py`
- If needed: `README.md`
- If needed: `.env.example`

1. 明确哪些配置是：
   - 必填
   - 可选
   - 仅用于集成模式
2. 明确日志级别和关键日志点，保证值班时能定位：
   - runner 生命周期
   - maintenance cycle
   - hook 注册尝试/失败/成功
   - runtime invoke 提交与失败

---

## 推荐实现顺序

建议按下面顺序推进，而不是同时铺开：

1. **restart consistency 测试矩阵**
2. **SQLite WAL 与防爆内存 TTL 自动清理** (Critical)
3. **真实 OpenClaw contract 固化 (合 Trace ID 与 HITL)** 
4. **gateway/runtime 适配层错误处理增强**
5. **Result Hook 结合乐观锁的真实 invoke/result 闭环** (Critical)
6. **部署文档与 smoke 流程硬化**

这样可以避免：

- 跑在线上时突然爆出 `Database is locked`
- Webhook 网络抖动引发状态机死胡同
- 出了问题全链路像黑洞一样抓瞎

---

## 验收标准

下一阶段完成后，应满足：

1. `master` 分支下，runner 在持久化 DB 模式下可重启并正确恢复任务推进
2. sidecar 与 OpenClaw 的 ingress / invoke / result contract 有明确文档与测试覆盖
3. runtime submission、hook callback、probe failure 都有稳定错误语义
4. 运维同学可以按文档完成最小试运行与排障
5. 以下验证命令稳定通过：
   - `pytest tests -q`
   - `python -m compileall sidecar`

---

## 建议接手提示

> 下一阶段不要再把重点放在“角色包装”或“新故事文案”上，而应围绕 `service_runner` 的恢复一致性、`openclaw_runtime` 的真实接线能力、以及部署/运维最小可落地性来推进。先用测试把 restart + invoke/result contract 打稳，再继续向试运行靠拢。
