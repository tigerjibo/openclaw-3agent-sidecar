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
   - 前置落实 SQLite WAL + busy_timeout（Task 0，基础设施级，5 分钟搞定）
   - 验证重启后 maintenance / recovery / dispatch 的一致性
   - 梳理 Result / Dispatch 的事务原子性边界，减少半写状态暴露窗口
   - 补充真实 restart / stale / blocked / timeout 回归覆盖

2. **真实 OpenClaw 接线闭环与链路追踪**
   - 让 runtime bridge / gateway hooks 从 skeleton 走向实际可配置接线
   - 固化 Trace ID 的贯穿机制（ingress -> invoke -> hook），使得 Sidecar 与 OpenClaw 间不再是可观测性黑洞
   - 定义人工干预（HITL）API Contract（如 `/runtime/unblock`），以解除 blocked 异常
   - 验证现有 `version` 乐观锁是否覆盖所有 Result Hook 回写路径（注意：代码已有 version 字段与校验，不需要重新实现）

> **评审纠偏**：原方案 Task 8 提出"引入 task_version 乐观锁"，但 `storage.py` schema 已有 `version INTEGER NOT NULL DEFAULT 1`，`result.py` 的每次状态流转均已在调用 `expected_version` 校验。因此 Task 8 应降级为**验证覆盖度**而非重新实现。

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

## Workstream 0：前置基础设施（立即执行）

### Task 0：SQLite WAL 模式与 busy_timeout

**Files:**
- Modify: `sidecar/storage.py`
- Create: `tests/test_storage_wal.py`

1. 在 `init_db()` 中加入 `PRAGMA journal_mode=WAL` 和 `PRAGMA busy_timeout=5000`。
2. 写一个测试验证：持久化 DB 模式下，WAL 已开启且 busy_timeout 已生效。
3. 这是最高优先级的前置改动——所有后续并发测试都依赖 WAL 正常工作。

> **为什么独立出来**：WAL 是基础设施层的一行 PRAGMA，不应与 TTL 归档（产品策略）绑定。TTL 归档移至 Workstream 3。

---

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

### Task 4：梳理 Result / Dispatch 事务原子性边界

**Files:**
- Modify: `sidecar/adapters/result.py`
- Modify: `sidecar/runtime/dispatcher.py`
- Modify: `sidecar/models.py`
- If needed: `tests/test_result_adapter.py`
- If needed: `tests/test_dispatcher.py`

> **评审发现的关键风险**：当前 `apply_result()` 一次回写涉及 4-6 次独立 `conn.commit()`。如果中间任何一步崩了（进程被 kill、磁盘满、OOM），任务将处于半写状态——事件写了但状态没推进，或者状态推进了但 dispatch 标记没清除。这比乐观锁问题更严重。

1. 梳理 `apply_result` 中每一次 `commit()` 的位置和意图。
2. 评估是否可以将"事件写入 + 状态流转 + dispatch 标记清除"合并为单个 SQLite 事务。
3. 对 `dispatch_task` 做同样的梳理。
4. 补充"半写恢复"测试：模拟中途崩溃后重启，验证 recovery 能正确收口。

---

## Workstream 2：真实 OpenClaw 接线落地与并发防御

### Task 5：固化 sidecar 与 OpenClaw 的 contract（含 Trace ID / HITL）

**Files:**
- Modify: `docs/adapter-contract.md`
- Modify: `docs/architecture.md`
- Modify: `sidecar/contracts.py`
- Modify: `sidecar/adapters/ingress.py`
- Modify: `sidecar/adapters/agent_invoke.py`
- Modify: `sidecar/http_service.py`

1. 明确三类 contract：
   - ingress payload
   - runtime invoke payload
   - result callback payload
2. 标明必填字段、鉴权头、错误码语义，以及**必须包含的系统级 `trace_id` 用于全链路追踪隔离。**
3. 在 ingress 中自动生成或传入 `trace_id`，在 invoke payload 中携带，在 result callback 中要求原样返回，关键日志点强制打印。
4. 补充定义 **人工干预 (HITL) `/runtime/unblock` HTTP 端点**——`api.py` 已有 `/tasks/{id}/unblock` 路由和 `clear_task_blocked()` 实现，但 `http_service.py` 尚未暴露到 HTTP 控制面。补上这个端点并加测试。

### Task 6：增强 gateway/runtime 适配层错误处理

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

> **注意**：Task 7 依赖 Task 4（事务原子性）和 Task 5（Trace ID）的完成。

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

### Task 8：验证现有 version 乐观锁覆盖度（降级为验证任务）

**Files:**
- Modify: `tests/test_result_adapter.py`（补充覆盖度测试）
- If needed: `sidecar/adapters/result.py`

> **评审纠偏**：原方案建议"引入 task_version 字段"，但 `storage.py` 的 tasks schema **已有** `version INTEGER NOT NULL DEFAULT 1`，`result.py` 中 `_apply_coordinator_success` / `_apply_executor_success` / `_apply_reviewer_success` **已经在每次状态流转时传入 `expected_version`**。因此本 Task 降级为验证 + 补漏。

1. 验证 `block` 和 `failed` 分支是否也经过了 version 校验（当前代码中 block 路径绕过了 `expected_version` 检查，需要确认是否为有意为之）。
2. 验证 `dispatch_task` 清除 dispatch 状态时是否校验了 version。
3. 补充一个"并发重复 Result 回写"测试：同一 invoke_id 在毫秒级连发两次，验证幂等拦截生效。
4. 如果发现覆盖缺口，补最小修复。

---

## Workstream 3：部署与运维硬化

### Task 9：把部署样例升级为试运行手册（含 TTL 归档策略）

> **TTL 归档从原 Task 4 拆出至此**：数据生命周期管理属于运维策略，不应与 WAL 基础设施绑定。

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
3. 补一段“本地试运行 smoke 流程”。4. 补充数据生命周期约定：已完结任务和事件的归档/清理策略（如 30 天 TTL），作为运维 SOP 的一部分记录。
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

0. **SQLite WAL + busy_timeout** (前置, 5 分钟)
1. **restart consistency 测试矩阵**
2. **运行态持久化边界梳理**
3. **shutdown/startup 收口语义**
4. **Result / Dispatch 事务原子性梳理** (Critical)
5. **Trace ID 贯穿 + HITL unblock 端点 + contract 固化**
6. **gateway/runtime 适配层错误处理增强**
7. **真实 invoke/result 最小闭环**
8. **version 乐观锁覆盖度验证**（验证 + 补漏，非重新实现）
9. **部署/运维硬化 + TTL 归档策略**
10. **smoke 验证 + 配置/日志约束**

这样可以避免：

- 跑在线上时突然爆出 `Database is locked`（Task 0 前置解决）
- Result 半写导致状态机残留不一致态（Task 4 解决）
- Webhook 重复到达导致假脑裂（Task 8 验证现有防线）
- 出了问题全链路像黑洞一样抓瞎（Task 5 Trace ID 解决）

---

## 验收标准

下一阶段完成后，应满足：

1. `master` 分支下，SQLite 持久化 DB 使用 WAL 模式，runner 可重启并正确恢复任务推进
2. Result / Dispatch 的关键写入路径在单个 SQLite 事务内完成，不存在半写暴露窗口
3. 全链路 Trace ID 从 ingress 贯穿到 invoke 和 result callback，关键日志可按 trace_id 检索
4. `/runtime/unblock` 端点可通过 HTTP 解除 blocked 任务
5. sidecar 与 OpenClaw 的 ingress / invoke / result contract 有明确文档与测试覆盖
6. runtime submission、hook callback、probe failure 都有稳定错误语义
7. 现有 version 乐观锁覆盖所有 Result 回写路径（含 block/failed 分支）
8. 运维同学可以按文档完成最小试运行与排障
9. 以下验证命令稳定通过：
   - `pytest tests -q`
   - `python -m compileall sidecar`

---

## 建议接手提示

> 下一阶段不要再把重点放在“角色包装”或“新故事文案”上，而应围绕 `service_runner` 的恢复一致性、`openclaw_runtime` 的真实接线能力、以及部署/运维最小可落地性来推进。先用测试把 restart + invoke/result contract 打稳，再继续向试运行靠拢。
---

## 评审修订记录

本计划经过同行评审后做了以下关键修订：

1. **新增 Task 0**：SQLite WAL + busy_timeout 作为前置基础设施独立出来，不与 TTL 归档绑定
2. **新增 Task 4**：Result / Dispatch 事务原子性梳理——评审发现 `apply_result()` 一次回写涉及 4-6 次独立 commit，存在半写状态风险，比乐观锁问题更严重
3. **Task 8 降级**：从"实现乐观锁"改为"验证现有 version 校验覆盖度"——代码已有 version 字段和 expected_version 校验
4. **TTL 归档拆出**：从原 Task 4 移至 Workstream 3（Task 9），作为运维策略而非基础设施
5. **修复编号**：消除原计划中重复的 Task 5，补回 Task 6
6. **HITL 端点具体化**：从"定义 API Contract"改为"在 http_service.py 暴露 /runtime/unblock 端点"——api.py 已有实现但未暴露到 HTTP 层