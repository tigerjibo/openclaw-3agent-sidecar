# Phase 0 Agent Inventory and Candidate Discovery Design

> 记录日期：2026-03-15
>
> 目标：为 `openclaw-3agent-sidecar` 的真实 3-agent 路线完成 Phase 0 设计，确保后续 rollout 以 upstream agent 证据而不是主观判断为基础。

---

## 背景

当前 sidecar 已经具备：

- 固定三角色状态机：`coordinator / executor / reviewer`
- CLI bridge 与 result callback 闭环
- reviewer-only AWS staging 验证
- `reviewer -> sysarch` 的真实会话证据

但这仍不等于真实 3-agent。当前 AWS staging 的实际形态是：

- `reviewer -> sysarch`
- `coordinator -> main`（fallback）
- `executor -> main`（fallback）

因此当前真正的 blocker 不是 sidecar 代码无法工作，而是：

> **upstream agent inventory 不完整，无法为 `coordinator` / `executor` 指派高置信度独立候选。**

---

## 目标

本设计的目标不是直接切换 role mapping，而是完成一套可重复、可审计、可决策的 Phase 0 方法，用来回答：

1. 目标环境中有哪些真实可用的 upstream agents
2. 哪些候选更适合 `coordinator`
3. 哪些候选更适合 `executor`
4. 当前是否具备进入 `coordinator` 扩展验证（Phase 2）的条件

---

## 备选路径与推荐

### 路径 A：快版 inventory

只快速拉取当前环境的 agent 名单与基础可见性证据，尽快输出一版 go / no-go。

**优点：** 快，1 天内可给出初步判断。  
**缺点：** 容易把“可见”误当“可用”，容易低估角色匹配风险。

### 路径 B：稳版 inventory + 角色判断 + 置信度分层

除了收集 inventory，还要求：

- 候选最小验证
- 角色倾向判断
- `High / Medium / Low` 置信度分层
- 明确 go / no-go 决策

**优点：** 决策质量高，能防止误启动 rollout。  
**缺点：** 比快版更慢，需要 1~2 天。

### 路径 C：继续契约补强后再做 inventory

先继续强化 callback / stale 等内部契约，再回来做 candidate 发现。

**优点：** 内部边界更稳。  
**缺点：** 回避了当前真正 blocker，不适合作为主线。

### 推荐

推荐 **路径 B（稳版）**。

理由：当前系统的主问题不是内部链路不通，而是外部 agent 资源条件不清楚。稳版能最大程度避免：

- 把共享 agent 误当 full 3-agent
- 把名字当能力证明
- 把单次成功误判成稳定可 rollout

---

## 范围

### 本设计覆盖

- upstream agent inventory 的采集与记录
- 候选 agent 的最小验证
- 候选角色倾向判断
- 候选置信度分层
- go / no-go 判定规则
- Phase 0 的输出物定义

### 本设计不覆盖

- 直接修改正式 `.env` role mapping
- 直接开始 `coordinator` / `executor` rollout
- production 3-agent 切换
- OpenClaw 核心源码修改

---

## 架构与组件边界

Phase 0 作为一个设计与验证阶段，逻辑上分成四个组件：

### 1. Inventory Collector

负责从多个来源采集候选 agent：

- 主机上的 agent 目录
- CLI 可列举结果（若支持）
- 近期 session / 日志
- 文档、runbook、运维清单

### 2. Candidate Verifier

负责对候选进行最小验证，关注：

- 是否真实存在
- 是否可调用
- 是否有近期活跃证据

### 3. Role Classifier

负责判断候选更像哪类角色：

- `coordinator-oriented`
- `executor-oriented`
- `reviewer-oriented`

角色分类必须依据证据，而不是只依据命名。

### 4. Decision Gate

负责根据候选置信度和基线状态，输出：

- `Go`
- `No-Go`

并明确 blocker 是什么。

---

## 数据流

稳版 Phase 0 的数据流如下：

1. 收集 upstream agent inventory
2. 形成 inventory 初表
3. 对候选做最小验证
4. 对候选做角色倾向判断
5. 对候选做置信度分层
6. 输出 `Go` / `No-Go`
7. 写出候选映射草案或 blocker

### 可视化流程

```text
发现 -> 验证 -> 分类 -> 分层 -> 决策 -> 输出
```

---

## 候选判断规则

### 候选最低证据链

一个 agent 至少满足下面两条，才应进入候选池：

- 能在主机上被发现（目录、CLI 或配置能证明）
- 有实际 session / 调用痕迹，或能被成功 invoke

### 角色倾向判断

#### `coordinator-oriented`

更适合作为 `coordinator` 的候选通常表现为：

- 目标澄清能力强
- 能稳定输出结构化规划 JSON
- 更偏拆解、定义 acceptance，而不是直接执行

#### `executor-oriented`

更适合作为 `executor` 的候选通常表现为：

- 更偏交付与结果摘要
- 能按约束执行步骤
- 更像承办者，而不是重新定义问题的人

#### `reviewer-oriented`

更适合作为 `reviewer` 的候选通常表现为：

- 风险识别、批判与拒绝能力更强
- 审阅意见明确
- 不倾向直接替代执行者完成任务

当前 `sysarch` 已被高置信度归到这一类。

---

## 置信度分层

### High

同时满足：

- 主机上明确存在
- 能成功调用
- 有近期 session / 调用证据
- 与目标角色高度匹配
- 至少经过一次以上稳定验证
- 当前没有明显契约漂移或异常模式

### Medium

满足部分条件，但仍缺关键证据，例如：

- 主机上可见
- 可能可调用
- 角色倾向初步明确
- 但缺稳定调用证据或重复验证

### Low

任一情况出现即归为 Low：

- 只有名字，没有主机证据
- 有目录，但不可调用
- 可调用，但角色倾向不清楚
- 仅单次弱证据，稳定性未知

### 使用原则

- `Medium` 只能进入“继续验证”，不能直接进入 role rollout
- `High` 才能进入下一阶段候选集
- `coordinator` / `executor` 进入 Phase 2/3 前必须至少 `High`

---

## Go / No-Go 规则

### Go

只有满足以下条件，才能从 Phase 0 进入 Phase 2：

- `reviewer` 候选已稳定（当前即 `sysarch`）
- 至少找到一个 `coordinator` 候选
- 该候选达到 `High`
- reviewer-only 基线仍健康可回退
- 证据链完整：
  - `ops/summary`
  - `recent_submission`
  - upstream session / logs

### No-Go

出现以下任一情况，都应停留在 Phase 0：

- 找不到 `coordinator` 候选
- 候选不是 `High`
- 候选职责倾向不清晰
- 候选不可稳定调用
- reviewer-only 基线不够稳
- 证据链不完整

### 明确 blocker 命名

当结论为 `No-Go` 时，应明确命名 blocker，例如：

- `upstream agent supply gap`
- `missing coordinator-grade upstream agent`
- `missing executor-grade upstream agent`

---

## 输出物

Phase 0 完成后，必须留下以下产物：

1. 一份 upstream agent inventory 记录
2. 一份候选角色判断记录
3. 一份 `Go` / `No-Go` 结论
4. 一份下一步动作建议：
   - 若 `Go`：进入 Phase 2 设计
   - 若 `No-Go`：明确新增 agent 需求或继续调查路径

### 结论格式

#### Go 示例

```text
reviewer -> sysarch (high, validated)
coordinator -> <candidate> (high, validated for Phase 2 entry)
executor -> no confirmed candidate yet
decision -> GO for Phase 2 (coordinator expansion only)
```

#### No-Go 示例

```text
reviewer -> sysarch (high, validated)
coordinator -> no confirmed candidate
executor -> no confirmed candidate
decision -> NO-GO
blocker -> upstream agent supply gap
```

---

## 错误处理与风险控制

### 风险 1：把“存在”误判成“可用”

对策：目录存在不能直接升级为候选，必须补可调用或 session 证据。

### 风险 2：把“可用”误判成“适合该角色”

对策：角色判断必须附带具体行为特征与证据，不允许只写“感觉像”。

### 风险 3：把“共享 agent”误判成“真实 3-agent”

对策：两角色共享一个 agent 只能记为机制验证，不能记为 full 3-agent。

### 风险 4：模糊结论导致错误 rollout

对策：Phase 0 只允许两种结束状态：`Go` 或 `No-Go`，禁止“先试试看”的模糊结论。

### 风险 5：调研产物无法复用

对策：所有结论必须回写为文档化产物，而不是停留在聊天里。

---

## 测试与验证策略

Phase 0 虽然不是代码实现任务，但仍需要验证：

### 事实验证

- inventory 中的 agent 是否真实存在
- session / 日志证据是否可回看
- 可调用结论是否有实际依据
- reviewer-only 基线是否仍健康

### 决策验证

- 为什么是 `High` 而不是 `Medium`
- 为什么它偏 `coordinator` 而不是 `reviewer`
- 为什么当前结论是 `Go` 或 `No-Go`

---

## 成功标准

Phase 0 的成功不要求立刻进入 3-agent，但必须达到以下之一：

### 成功输出 A：可推进

- 已识别 `coordinator` 候选
- 已识别 `executor` 候选或明确仍待后续发现
- `reviewer` 候选已稳定
- 能进入 Phase 2

### 成功输出 B：明确阻塞

- `reviewer` 候选已稳定
- `coordinator` / `executor` 候选仍缺失
- blocker 已被明确命名
- 不再假装可以直接进入真实 3-agent

---

## 一句话结论

> Phase 0 的核心不是立刻切配置，而是先建立一套可重复的证据机制，证明哪些 upstream agent 真正有资格进入 3-agent rollout。只有这件事搞清楚，后面的真实 3-agent 才不是空中楼阁。
