# Recovery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 `openclaw-3agent-sidecar` 实现首版 `sidecar/runtime/recovery.py`，使 sidecar 能在重启、超时、阻塞等场景下对任务进行最小恢复与收口。

**Architecture:** 以现有 `dispatcher`、`scheduler`、`metrics`、`task_events` 为基础，新增 `recovery.py`。Recovery 首版不直接执行复杂业务动作，而是优先完成：识别异常任务、释放错误的 in-flight 状态、记录恢复事件、对 timeout/block 场景做最小 retry / escalate 标记。

**Tech Stack:** Python 3.9+、SQLite、pytest、现有 sidecar task kernel/runtime。

---

## 设计边界

### 首版 recovery 要做

1. **重启恢复**
   - 启动时扫描 `dispatch_status='running'` 但实际未完成的任务
   - 释放 dispatch in-flight 标记
   - 写入 `task.recovered` 事件

2. **超时恢复**
   - 基于 `metrics.get_state_entry_time()` 判断：
     - `executing` 超时
     - `reviewing` 超时
   - 为超时任务记录恢复事件
   - 首版只做最小动作：
     - 释放 dispatch 状态
     - 增加 attempt / recovery note
     - 交还给 scheduler 再次派发或等待人工处理

3. **阻塞任务扫描**
   - 对 `blocked=1` 且持续时间超过阈值的任务打出恢复/升级事件
   - 首版不自动解除 blocker，只做事件与状态收口

4. **最小 retry / escalate 语义**
   - 增加恢复动作枚举：
     - `recover_dispatch`
     - `retry_dispatch`
     - `escalate_blocked`
     - `escalate_timeout`
   - 首版允许：
     - 对 dispatch 丢失场景自动 retry 一次
     - 对 blocked/timeout 场景打 escalation 事件

### 首版 recovery 不做

- 不直接修改官方 OpenClaw runtime
- 不做复杂退避算法
- 不做多层升级链路
- 不做完整通知系统
- 不做重型 UI

---

## 建议新增/修改文件

### 新增

- `sidecar/runtime/recovery.py`
- `tests/test_recovery.py`

### 可能修改

- `sidecar/runtime/scheduler.py`
- `sidecar/service_runner.py`
- `sidecar/metrics.py`
- `sidecar/contracts.py`
- `sidecar/storage.py`（如需 recovery note / counters 字段）
- `sidecar/models.py`

---

## 数据与状态建议

### 可直接复用的现有字段

- `dispatch_status`
- `dispatch_role`
- `dispatch_started_at`
- `dispatch_attempts`
- `blocked`
- `block_since`
- `state`
- `current_role`
- `last_event_at`
- `last_event_summary`

### 首版可考虑新增字段（如需要）

- `recovery_attempts`
- `last_recovery_at`
- `last_recovery_reason`
- `escalated`

如果首版能只靠 `task_events` 落审计，则尽量不要急着加太多列，保持 YAGNI。

---

## 推荐实现顺序

### Task 1：写 recovery 失败测试（重启恢复）

**Files:**
- Create: `tests/test_recovery.py`
- Modify: `sidecar/runtime/recovery.py`

1. 写失败测试：当任务处于 `dispatch_status='running'` 且未完成时，recovery 能释放 in-flight 状态。
2. 运行测试，确认失败。
3. 实现最小 `recover_inflight_dispatches()`。
4. 再次运行测试，确认通过。

### Task 2：写 executing timeout 失败测试

1. 写失败测试：`state='executing'` 超时后，recovery 记录 timeout 事件并释放 dispatch。
2. 运行测试，确认失败。
3. 实现 `recover_execution_timeouts()`。
4. 再次运行测试，确认通过。

### Task 3：写 reviewing timeout 失败测试

1. 写失败测试：`state='reviewing'` 超时后，recovery 记录 timeout / escalate 事件。
2. 运行测试，确认失败。
3. 实现 `recover_review_timeouts()`。
4. 再次运行测试，确认通过。

### Task 4：写 blocked escalation 失败测试

1. 写失败测试：blocked 持续超过阈值后，recovery 记录 `escalate_blocked` 事件。
2. 运行测试，确认失败。
3. 实现 `recover_blocked_tasks()`。
4. 再次运行测试，确认通过。

### Task 5：组合 recovery loop

1. 实现统一入口，例如 `run_once()`。
2. 让它按顺序执行：
   - inflight recover
   - execution timeout recover
   - review timeout recover
   - blocked escalation
3. 增加汇总返回值，供 scheduler/service runner 调用。
4. 跑 `pytest tests -q` 与 `python -m compileall sidecar`。

---

## Recovery 首版接口建议

建议提供类似接口：

```python
class TaskRecovery:
    def recover_inflight_dispatches(self) -> list[str]: ...
    def recover_execution_timeouts(self) -> list[str]: ...
    def recover_review_timeouts(self) -> list[str]: ...
    def recover_blocked_tasks(self) -> list[str]: ...
    def run_once(self) -> dict[str, list[str]]: ...
```

这样便于：

- 单测逐个覆盖
- scheduler / service runner 统一调度
- 后续接 agent health 与运维指标

---

## 验收标准

首版完成后，应满足：

1. sidecar 重启后，错误残留的 in-flight dispatch 不会永久卡住任务
2. `executing` / `reviewing` 超时任务能被识别并写入恢复事件
3. 长时间 blocked 任务能被识别并写入 escalation 事件
4. recovery 不绕过任务状态机伪造 done
5. 所有新增行为有测试覆盖
6. 运行以下验证通过：
   - `pytest tests -q`
   - `python -m compileall sidecar`

---

## 推荐接手提示

> 在 `D:\code\openclaw-3agent-sidecar` 中以 TDD 方式优先实现 `sidecar/runtime/recovery.py`。先把 `tests_draft/test_recovery.py` 中的草稿场景转成正式 `tests/test_recovery.py`，逐个跑红灯、补最小实现、再跑全量验证。
