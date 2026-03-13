# Adapter Minimal Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为 `openclaw-3agent-sidecar` 落地最小可运行的 `ingress / invoke / result` 适配层闭环，并通过测试验证任务可从创建推进到 reviewer 决策。

**Architecture:** 在不改动现有 task kernel 主体的前提下，新增适配层模块。`ingress` 负责把外部制度化任务归一化并入库，`invoke` 负责为三角色生成稳定调用载荷，`result` 负责解析角色结构化结果并回写任务字段与状态。首版使用内存/本地 DB 与直接函数调用方式验证闭环。

**Tech Stack:** Python 3.9+、SQLite、pytest、sidecar task kernel。

---

### Task 1: 写 ingress 失败测试

**Files:**
- Create: `tests/test_ingress_adapter.py`
- Modify: `sidecar/adapters/ingress.py`

1. 写一个失败测试，验证标准 ingress payload 能创建 task，并用 `request_id` 保证幂等。
2. 运行该测试并确认失败。
3. 实现最小 ingress adapter。
4. 再次运行测试并确认通过。

### Task 2: 写 invoke 失败测试

**Files:**
- Create: `tests/test_agent_invoke_adapter.py`
- Modify: `sidecar/adapters/agent_invoke.py`

1. 写一个失败测试，验证给定 task + role 能生成稳定 invoke payload。
2. 运行该测试并确认失败。
3. 实现最小 invoke adapter。
4. 再次运行测试并确认通过。

### Task 3: 写 result 失败测试

**Files:**
- Create: `tests/test_result_adapter.py`
- Modify: `sidecar/adapters/result.py`

1. 写失败测试，覆盖 coordinator / executor / reviewer 三类结果回写与状态推进。
2. 运行测试并确认失败。
3. 实现最小 result adapter。
4. 再次运行测试并确认通过。

### Task 4: 跑最小闭环验证

**Files:**
- Modify: `tests/test_end_to_end_minimal_loop.py`
- If needed: `sidecar/adapters/*.py`

1. 写一个最小端到端测试：ingress -> invoke payload -> result 回写 -> reviewer approve/reject。
2. 运行测试确认先失败。
3. 补最小代码使其通过。
4. 运行 `pytest tests -q` 与 `python -m compileall sidecar` 做最终验证。
