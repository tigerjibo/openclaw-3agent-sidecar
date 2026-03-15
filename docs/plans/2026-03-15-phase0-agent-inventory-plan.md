# Phase 0 Agent Inventory and Candidate Discovery Plan

> 记录日期：2026-03-15
>
> 目标：为 `openclaw-3agent-sidecar` 的真实 3-agent 路线完成 Phase 0 —— 在目标环境中识别、验证并命名 `coordinator / executor / reviewer` 的 upstream agent 候选。

---

## 1. 为什么要先做 Phase 0

当前 sidecar 已具备：

- 固定三角色状态机
- CLI bridge
- result callback 闭环
- reviewer-only staging 验证

但真实 3-agent 还没有开始，原因不是 sidecar 不工作，而是：

- 当前 AWS staging 仅确认存在 `main` 与 `sysarch`
- `reviewer -> sysarch` 已验证通过
- `coordinator` / `executor` 仍 fallback 到 `main`

因此当前的真正 blocker 是：

> **上游 agent inventory 不完整，无法为 coordinator / executor 指派可信的独立候选。**

Phase 0 的目的就是先解决这个 blocker。

---

## 2. Phase 0 的交付物

Phase 0 完成后，应至少产出以下内容：

1. 一份当前目标环境中的 upstream agent inventory
2. 一份候选映射草案：
   - `coordinator -> ?`
   - `executor -> ?`
   - `reviewer -> ?`
3. 每个候选的用途判断与证据
4. 一个 go / no-go 决策：
   - 能否进入 Phase 2（coordinator 扩展验证）
   - 若不能，缺什么
5. 若缺失候选，明确新增 / provision 请求项

---

## 3. 当前已知事实（2026-03-15）

截至当前，已确认：

### 3.1 sidecar staging 现状

- sidecar 服务健康
- `runtime_invoke_ready`
- `reviewer -> sysarch`
- `coordinator -> main`
- `executor -> main`

### 3.2 当前已见 upstream agents

在 AWS 主机上已观察到：

- `main`
- `sysarch`

以及已知不可用历史候选：

- `work` → `Unknown agent id`

### 3.3 当前结论

- `reviewer` 候选已有：`sysarch`
- `coordinator` 专用候选：**未知 / 未确认**
- `executor` 专用候选：**未知 / 未确认**

因此当前**不能直接宣称已具备真实 3-agent 的资源条件**。

---

## 4. Phase 0 的核心问题

需要回答的不是“我们想不想做 3-agent”，而是下面这四个问题：

1. 目标环境里到底有哪些可用 agent？
2. 哪些 agent 的职责更适合 `coordinator`？
3. 哪些 agent 的职责更适合 `executor`？
4. 哪些 agent 已足够稳定，能承接 staging 放量？

---

## 5. 执行步骤

### 5.1 收集 inventory 来源

优先从以下来源收集 agent 名单：

1. 目标主机上的 agent 目录
2. OpenClaw CLI 可列举结果（如果可用）
3. 近期 upstream session 目录
4. 运维 / 平台侧维护清单
5. 现有文档、runbook、历史验证记录

### 推荐最低证据链

一个 agent 只有在至少满足下面两条时，才应进入候选池：

- 能在主机上被发现（目录、CLI 或配置能证明）
- 有实际 session / 调用痕迹，或可被成功 invoke

---

### 5.2 做第一轮 inventory 表

建议建立一张候选表，字段至少包含：

- `agent_id`
- `source_of_truth`
- `discoverability`
- `recent_session_seen`
- `invokeable`
- `suggested_role`
- `confidence`
- `notes`

### 表结构示例

| agent_id | 来源 | 最近 session | 可调用 | 建议角色 | 置信度 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| `main` | agent dir / current config | yes | yes | fallback only | high | 当前仍作为 fallback |
| `sysarch` | agent dir / reviewer proof | yes | yes | reviewer | high | 已完成 reviewer-only 验证 |
| `<candidate>` | TBD | TBD | TBD | coordinator/executor | low/med/high | 待验证 |

---

### 5.3 做职责判断，而不是只看名字

不要仅根据 agent 名称做决定。

需要根据实际能力，把候选分为三类：

### A. Planning / coordinator-oriented

更适合作为 `coordinator` 的候选通常表现为：

- 目标澄清能力强
- 能稳定输出结构化规划 JSON
- 更少直接“开干”，更多先拆解与定义 acceptance
- 在历史 session 中体现出较强的规划与审阅习惯

### B. Execution / executor-oriented

更适合作为 `executor` 的候选通常表现为：

- 能产出结果摘要与证据
- 能按约束执行步骤
- 更适合落实而不是重新定义目标
- 响应中更偏交付与证据，而非纯批判

### C. Review / reviewer-oriented

更适合作为 `reviewer` 的候选通常表现为：

- 拒绝 / 质疑 / 风险识别更强
- 能输出明确审阅意见
- 不倾向直接替代执行者完成任务
- 能稳定给出 approve / reject 语义

当前 `sysarch` 已有较高把握归入这一类。

---

### 5.4 对候选做最小验证

在不动正式 role mapping 前，先对候选做“最小验证”，建议分三级：

### Level 1 — 被动证据验证

目标：确认它确实存在且最近被使用过。

证据包括：

- agent 目录存在
- 最近 session 文件存在
- 日志里出现对应 agent 名称

### Level 2 — CLI 可调用验证

目标：确认它至少不是死配置。

如果环境允许，可尝试：

- 列举 agent
- 对候选 agent 做一次最小 invoke / probe

### Level 3 — sidecar 路由前的实验性角色判断

目标：判断它更像 coordinator / executor / reviewer 哪一类。

建议通过：

- 读近期 session 风格
- 如可能，做一次小型提示实验
- 看输出是偏规划、偏执行还是偏审阅

注意：

- Level 3 只是候选分类，不等于已可用于正式 rollout
- 候选分类要靠证据，不靠命名想象

---

### 5.5 形成候选映射草案

Phase 0 结束时，应至少写出一版草案：

### 目标草案格式

```text
reviewer -> sysarch (high confidence, already validated)
coordinator -> <candidate> (confidence: med/high)
executor -> <candidate> (confidence: med/high)
main -> fallback only
```

### 如果拿不到完整草案

那就必须诚实输出 blocker，例如：

```text
reviewer -> sysarch (confirmed)
coordinator -> no confirmed candidate
executor -> no confirmed candidate
blocker -> upstream agent inventory incomplete
```

这同样是 Phase 0 的有效输出，只是不是 go 结果，而是 no-go 结果。

---

## 6. Go / No-Go 判定规则

### 6.1 可以进入 Phase 2（Go）

只有满足以下条件，才建议进入 coordinator 扩展验证：

- reviewer 候选已稳定（当前满足）
- coordinator 候选已确认真实存在
- coordinator 候选可调用
- 至少有一条较强证据说明它偏 planning / coordinator
- 当前 reviewer-only 基线仍健康可回退

### 6.2 不应进入 Phase 2（No-Go）

以下任一情况出现，都应停留在 Phase 0：

- 找不到 coordinator 候选
- 候选只存在于口头说法里，没有主机证据
- 候选不可调用
- 候选职责明显更像 reviewer 或 executor
- sidecar 当前 staging 已不稳定

### 6.3 不应混淆的情况

下面这些都**不能**算作通过 Phase 0：

- 仅知道有 `main`
- 想当然认为 `sysarch` 可以兼任所有角色
- 只看到名字，没有 session / invoke 证据
- 因为想推进 3-agent，就把共享 agent 说成独立 agent

---

## 7. 建议的实际执行命令/检查点

以下是建议在远端逐项做的检查类型。

### 7.1 发现 agent 名单

- agent 目录
- CLI 列举（若支持）
- 历史 session 所在目录

### 7.2 验证当前 sidecar 基线

- `/healthz`
- `/readyz`
- `/ops/summary`
- 当前 `.env` role mapping

### 7.3 观察候选 session 风格

优先看：

- 是否偏规划
- 是否偏执行
- 是否偏审阅
- 是否稳定输出结构化内容

### 7.4 记录 inventory 结果

建议把 inventory 结果最终写回：

- `docs/plans/...` 中的后续验证记录
- 或新建一份 agent inventory note

---

## 8. 风险与误判点

### 风险 1：把“存在”误判成“可用”

一个 agent 目录存在，不代表它真的能稳定 invoke。

### 风险 2：把“可用”误判成“适合该角色”

一个 agent 可以调用，不代表适合当 coordinator 或 executor。

### 风险 3：把“共享 agent”误判成“真实 3-agent”

两个角色共用 `sysarch` 只能验证路由机制，不能证明 full 3-agent。

### 风险 4：把命名当成能力证明

`planner-*` 并不一定真的会规划，`worker-*` 也不一定真的适合执行。

### 风险 5：只看单次输出

单次成功不代表稳定，至少需要多源证据或重复验证。

---

## 9. 推荐时间盒

建议把 Phase 0 控制在 **1 到 2 个工作日** 内完成初版结论：

### Day 1

1. 收集 inventory
2. 建立候选表
3. 确认现有证据链
4. 输出第一版 mapping 草案

### Day 2

1. 对 coordinator / executor 候选做最小验证
2. 完成 go / no-go 判定
3. 若 go，准备 Phase 2 rollout
4. 若 no-go，明确提出新增 agent 需求

---

## 10. 成功标准

Phase 0 完成，不要求立即进入 3-agent，但必须达到以下之一：

### 成功输出 A：可推进

- 已识别 coordinator 候选
- 已识别 executor 候选
- reviewer 候选已稳定
- 可以进入 Phase 2

### 成功输出 B：明确阻塞

- reviewer 候选已稳定
- coordinator / executor 候选仍缺失
- blocker 已被明确命名为“upstream agent supply gap”
- 不再假装可以直接进入真实 3-agent

这两种都比“继续含糊推进”更成功。

---

## 11. 当前最务实的一句话结论

> Phase 0 的核心不是立刻切配置，而是先把上游 agent 资源盘清楚：谁真实存在、谁能调用、谁更像 coordinator、谁更像 executor。只有这件事搞清楚，后面的真实 3-agent 才不是空中楼阁。
