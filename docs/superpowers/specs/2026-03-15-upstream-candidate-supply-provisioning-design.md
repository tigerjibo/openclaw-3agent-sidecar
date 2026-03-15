# Upstream Candidate Supply / Provisioning Design

> 记录日期：2026-03-15
>
> 目标：在 Phase 0 已明确 `NO-GO` 与 `upstream agent supply gap` 之后，为真实 3-agent 路线定义下一子项目的双轨设计：先做短时发现，再在必要时转入供给 / provisioning 规格化。

---

## 背景

当前 `openclaw-3agent-sidecar` 已经完成：

- 固定三角色状态机：`coordinator / executor / reviewer`
- sidecar 作为任务真相源的基础闭环
- CLI bridge 与 result callback 基线
- reviewer-only AWS staging 验证
- Phase 0 inventory 执行与证据归档

截至 2026-03-15，AWS staging 的已确认真实状态仍然是：

- `reviewer -> sysarch`
- `coordinator -> main`（fallback）
- `executor -> main`（fallback）

已确认可见 upstream agent 只有：

- `main`
- `sysarch`

Phase 0 的结论已经收敛为：

```text
reviewer -> sysarch (high, validated)
coordinator -> none (no confirmed high-confidence candidate)
executor -> none (no confirmed high-confidence candidate)
decision -> NO-GO
blocker -> upstream agent supply gap
```

因此，下一步的主问题已不再是“sidecar 是否支持 3-agent 语义”，而是：

> **如何以最短、最诚实、最可审计的方式，确认是否还存在未登记候选；若没有，就把上游 agent 供给需求规格化，而不是继续空转调查。**

---

## 目标

这个子项目的目标不是直接改动 live role mapping，也不是立刻进入 full rollout，而是完成以下两件事之一：

1. 在短时发现窗口内找到新的真实候选 upstream agent，并确认它是否具备进入后续 rollout 设计的资格。
2. 如果短时发现未产出新候选，则把缺失的 `coordinator` / `executor` 供给需求正式化，形成可交付的 provisioning 规格与验证入口契约。

换句话说，本设计要解决的是：

- 何时停止继续“找”
- 何时切换到“补供给”
- 供给补的到底是什么
- 后续怎样验证新增候选不是假阳性

---

## 备选路径与推荐

### 路径 A：发现型

继续围绕现有 AWS / upstream 环境扩大 inventory 调查，直到找到足够候选为止。

**优点：** 改动最少，理论上不需要新增上游资源。  
**缺点：** 容易无限期拖延，且会把“没有更多候选”伪装成“还没找够”。

### 路径 B：供给型

直接接受当前 host 上缺少 `coordinator-grade` / `executor-grade` 候选的现实，立刻转入新增 / provision 专用 upstream agent 的规格定义。

**优点：** 直面 blocker，行动最聚焦。  
**缺点：** 如果其实存在未登记但可用的候选，会跳过一轮低成本确认。

### 路径 C：双轨型

先做一个严格 time-box 的短时发现 Gate；如果没有拿到可用新候选，就立即切换到 provisioning 轨道，不再无限延长发现工作。

**优点：** 既避免漏掉现成资源，又防止调研无止境；最适合当前已明确 blocker、但仍允许一次低成本复核的状态。  
**缺点：** 需要更明确的切换门槛，否则容易名义双轨、实则反复横跳。

### 推荐

推荐 **路径 C（双轨型）**。

理由：

- Phase 0 已经证明当前 blocker 是 supply gap，而不是 sidecar 内部机制缺失。
- 继续长时间 discovery 的收益很低，但完全跳过 discovery 也会丢掉“低成本确认隐藏候选”的最后窗口。
- 双轨型允许先做一次短、硬、可判定的复核；如果没有结果，就马上进入 provisioning，不再用“再看看”拖住真实 3-agent 路线。

---

## 范围

### 本设计覆盖

- Gate 1：短时 candidate discovery
- Gate 2：candidate supply / provisioning 规格化
- candidate 等级定义
- Gate 1 → Gate 2 的切换规则
- provisioning 输出物定义
- 新增候选进入后续 rollout 设计前的验证入口约束

### 本设计不覆盖

- 直接修改 AWS staging live `.env`
- 直接执行 `coordinator` / `executor` role mapping rollout
- production 部署自动化实现
- OpenClaw 核心代码修改
- 把共享 agent 包装成“真实 3-agent”

---

## 核心设计原则

1. **先判定，再推进。** discovery 必须有明确结束条件，不能无限延长。
2. **供给问题按供给问题处理。** 若没有真实 candidate，就应转入 provisioning，而不是继续写更漂亮的调查结论。
3. **`main` 只能继续作为 fallback。** 它可以支撑兼容性与回退，但不能被包装成 dedicated `coordinator` / `executor` 候选。
4. **候选资格必须分级。** “被发现”不等于“可 rollout”。
5. **新增供给必须可验证。** 不允许只交付一个 agent 名称，而没有职责定义、命名约束和最小验证入口。
6. **当前真实状态必须诚实可表述。** 在新的 dedicated candidate 没出现前，系统仍应被描述为 reviewer-only role-specific routing，而不是 real 3-agent。

---

## 双轨架构

### Gate 1：Short Discovery

这是一个严格 time-box 的短时发现窗口，用于回答：

- 当前 upstream / host / 运维文档之外，是否还存在未登记但真实可用的 candidate
- 如果存在，它们是否至少达到 `discovery candidate` 的门槛

Gate 1 的目的不是再次做完整 Phase 0，而是做一次更窄、更快的复核。

### Gate 2：Provisioning

如果 Gate 1 没有产出满足条件的新候选，则立即转入 Gate 2，把当前 blocker 正式翻译为上游供给规格：

- 需要哪些角色类型的 agent
- 每类 agent 的职责边界是什么
- 建议命名与映射口径是什么
- 最小验证入口要证明什么

Gate 2 的目的不是立刻部署，而是先把“需要补什么”定义清楚，避免后续供给失焦。

---

## Gate 1：短时发现设计

### Gate 1 目标

在一个半天到一天的窗口内，完成对“是否还存在隐藏 candidate”的最终复核，并输出二元结果：

- `found candidate`
- `no additional candidate`

### Gate 1 时间边界

Gate 1 必须遵守以下硬约束：

- 最短可按半天收口
- 最长不超过 1 个工作日
- 不允许因为“可能还有别处没看”而无限延期

### Gate 1 可使用的证据来源

只允许使用与当前 blocker 直接相关的低成本来源，例如：

- host 上现有 agent 目录与 session 痕迹
- 当前运维 / rollout 文档中未交叉核对的 agent 命名线索
- upstream CLI / runtime 可直接确认的 agent 入口
- 明确的维护者口径或已存在 provisioning 记录

### Gate 1 明确禁止事项

Gate 1 期间不应做以下动作：

- 修改 live role mapping
- 把 `main` 临时解释成 dedicated `coordinator` 或 `executor`
- 为了证明“发现有价值”而扩大调查范围
- 新增不受约束的实验性部署

### Gate 1 输出格式

Gate 1 结束时只能输出以下两类之一：

#### 输出 A：发现到新候选

必须说明：

- candidate id
- 证据来源
- 初步角色倾向
- 是否已达到 `discovery candidate`
- 下一步是否需要进入 rollout-grade validation

#### 输出 B：未发现额外候选

必须说明：

- 本轮发现窗口已关闭
- 当前 blocker 仍是 `upstream agent supply gap`
- 进入 Gate 2 provisioning

---

## Gate 2：Provisioning 设计

### Gate 2 触发条件

出现以下任一情况时，必须进入 Gate 2：

- Gate 1 未发现任何新增 candidate
- Gate 1 发现了名字，但没有任何候选达到 `discovery candidate`
- Gate 1 候选无法证明具备清晰角色边界
- Gate 1 的新增候选仍不足以覆盖 `coordinator` / `executor` 供给缺口

### Gate 2 目标

把当前模糊的“缺 agent”翻译成一套明确的上游供给需求，至少覆盖：

- 缺哪两类角色能力
- 每类候选应承担什么责任
- 应采用什么命名 / 映射口径
- 新供给进入 staging 前最低要过哪些验证

### Gate 2 供给对象

优先针对以下两个缺口：

- `coordinator-grade` candidate
- `executor-grade` candidate

`reviewer` 当前已有 `sysarch` 作为高置信度基线，因此 Gate 2 不是为了重做 reviewer 供给，而是为了补齐真实 3-agent 缺的另外两条腿。

### Gate 2 输出内容

Gate 2 至少要产出三类规格：

1. **candidate supply spec**
   - 明确缺失角色类型
   - 说明每类角色的目标能力与非目标能力
2. **naming / mapping draft**
   - 定义建议 agent 命名风格
   - 定义 role -> agent 的预期映射口径
3. **validation entry contract**
   - 定义一个新增 candidate 在进入 rollout 设计前必须满足的最低验证条件

---

## Candidate 等级定义

### Level 1：discovery candidate

`discovery candidate` 指的是在 Gate 1 或 Gate 2 后首次进入候选池、但还不能直接用于 rollout 的对象。

至少需要满足：

- 有真实存在证据
- 不是纯历史名字或传闻命名
- 能与某个角色方向产生初步关联
- 不与已知无效候选事实冲突

它回答的是：

> “这是不是一个值得继续验证的真实对象？”

但它**不**回答：

> “这是不是已经可以拿去做 role rollout？”

### Level 2：rollout-grade candidate

`rollout-grade candidate` 是可以进入后续 rollout 设计与 staged validation 的候选。

至少需要满足：

- 已能明确映射到 `coordinator` 或 `executor` 中至少一个方向
- 有调用或等价运行证据
- 有近期活跃证据或当前可维护性证据
- 没有明显契约风险会直接破坏 sidecar 闭环
- 足以进入后续 Phase 2 / Phase 3 规划

它回答的是：

> “这个 candidate 是否已经具备进入 rollout 计划的最低资格？”

### 使用原则

- `discovery candidate` 只能进入进一步验证，不可直接宣称供给问题已解决。
- 只有 `rollout-grade candidate` 才能作为后续 role-specific rollout 设计输入。
- 如果一个角色方向始终没有 `rollout-grade candidate`，则该方向的 supply gap 仍然存在。

---

## 角色责任边界

### coordinator-grade 预期责任

供给中的 `coordinator-grade` candidate 应优先表现为：

- 更擅长拆解问题、定义目标与验收条件
- 能输出稳定的计划 / 结构化规划信息
- 不以“直接代做全部执行”为主

### executor-grade 预期责任

供给中的 `executor-grade` candidate 应优先表现为：

- 更擅长依据既定目标执行与交付
- 能输出结果摘要、证据、未决项
- 不以重新定义任务边界为主

### reviewer-grade 责任说明

本子项目不重做 reviewer 基线，但要明确：

- `sysarch` 仍是当前高置信度 reviewer-oriented baseline
- reviewer 方向不应被用来代替缺失的 coordinator / executor 专用供给

---

## 命名与映射草案

Gate 2 的命名草案不要求一次定死最终命名，但必须足够清晰，避免后续“名字像那个角色，所以先拿来用”的混乱。

建议采用以下口径：

- `coordinator` 对应 `coord-*` / `planner-*` 风格命名
- `executor` 对应 `exec-*` / `worker-*` 风格命名
- `reviewer` 对应 `review-*` 或当前稳定 reviewer agent 命名

命名草案必须服务于职责边界，而不是反过来让职责迁就名称。

如果 Gate 1 或后续供给流程发现了一个已存在但命名不符合上述建议的 candidate，仅凭命名不匹配不能直接取消资格；真实能力与角色证据仍然优先于命名风格本身。

同时必须明确：

- `main` 继续保留为 fallback / rollback / compatibility agent
- `main` 不是 steady-state dedicated role mapping 的命名答案

---

## 验证入口契约

新增 candidate 在进入后续 rollout 设计前，最小验证入口至少要回答以下问题：

1. **它真的存在吗？**
   - 能被 host、CLI、配置或维护记录中的至少一种强证据确认
2. **它真能被调用吗？**
   - 存在成功调用或等价可运行证据
3. **它更像哪个角色？**
   - 有证据支持 `coordinator-oriented` 或 `executor-oriented`
4. **它不会立刻破坏 sidecar 闭环吗？**
   - 没有已知的明显契约冲突会阻止后续验证
5. **它是否达到了 rollout-grade？**
   - 这是基于前 1~4 项结果的最终资格判定；前 1~4 项通过后，仍需显式确认该 candidate 已足以进入后续 rollout 计划，而不是自动升级
   - 若否，只能停留在 discovery 层级

只有通过这个入口契约的 candidate，才应进入下一轮 rollout 计划设计。

---

## 决策与转轨规则

### Gate 1 → Gate 2 硬切换条件

出现以下任一情况，必须从 Gate 1 切换到 Gate 2：

- 在 time-box 结束前仍无新增 candidate
- 发现的对象只有名称，没有真实存在证据
- 新候选无法区分角色倾向
- 新候选全部停留在 `discovery candidate`
- 即使发现 1 个新候选，整体仍无法补齐 `coordinator` / `executor` 的供给缺口

### 何时允许停留在 Gate 1 结果上

只有当 Gate 1 发现的新候选已经满足以下条件时，才允许先不进入 provisioning：

- 至少形成一个明确的后续验证对象
- 能说明它为何值得进入 rollout-grade validation
- 不会误导团队以为真实 3-agent 已经可直接推进

这时 Gate 1 的输出不是“问题解决”，而是：

- blocker 被部分缩小
- 后续转为 candidate validation / rollout planning

### 何时可以说 supply gap 缩小了

只有在至少一个缺口方向出现 `rollout-grade candidate` 时，才可以说 supply gap 被实质缩小。否则，仍应维持：

```text
blocker -> upstream agent supply gap
```

---

## 错误处理与风险控制

### 风险 1：无限 discovery

如果没有 time-box，双轨型会退化成“继续找找看”。

**对策：** Gate 1 必须有明确时间上限与固定输出格式。

### 风险 2：名字驱动误判

把看起来像 `planner-*` 的名字直接认定为 `coordinator-grade`，会制造假候选。

**对策：** 命名只能作为辅助线索，不能单独构成候选资格。

### 风险 3：把共享或 fallback 当成 dedicated 供给

这会让系统在仍依赖 `main` 时被误叫成 real 3-agent。

**对策：** 本设计明确禁止把 `main` 包装成 dedicated `coordinator` / `executor`。

### 风险 4：供给规格过宽

如果不定义责任边界，后续任何 agent 都能被硬塞进来，最终还是回到模糊状态。

**对策：** Gate 2 必须同时产出角色责任边界与验证入口契约。

### 风险 5：输出只停留在聊天中

这会导致后续计划重新丢上下文。

**对策：** 本设计要求将结论沉淀为 spec，并作为后续 implementation plan 的唯一输入之一。

---

## 测试与验证策略

虽然这个子项目本身以设计与规格化为主，但它必须为后续验证提供明确入口。

### 文档层验证

需要验证：

- Gate 1 / Gate 2 是否边界清晰
- candidate 等级是否互不混淆
- `main` 的 fallback 语义是否被保持
- 是否避免了“共享 agent = real 3-agent”的误表述

### 决策层验证

需要验证：

- 什么时候宣布 discovery 结束
- 什么时候宣布必须转入 provisioning
- 什么时候 candidate 仅是 `discovery candidate`
- 什么时候 candidate 才能升级为 `rollout-grade candidate`

### 与现有路线图的一致性验证

需要保持与以下事实一致：

- 当前真实基线仍是 reviewer-only role-specific routing
- `sysarch` 仍是 reviewer baseline
- `main` 仍是 fallback
- 当前 blocker 仍是 `upstream agent supply gap`

---

## 成功标准

这个子项目的成功不要求马上出现新 agent，但必须至少达成以下一种结果：

### 成功输出 A：发现成功

- 在 Gate 1 内找到至少一个真实新候选
- 该候选至少达到 `discovery candidate`
- 并形成是否继续做 rollout-grade validation 的明确判断

若出现该结果，后续优先进入 candidate validation / rollout planning；只有在 discovery 结果仍不足以覆盖 `coordinator` / `executor` 缺口时，才继续补做 Gate 2 provisioning 规格。

### 成功输出 B：供给规格完成

- Gate 1 明确关闭
- blocker 仍被诚实记录为 `upstream agent supply gap`
- Gate 2 已产出 candidate supply spec、naming / mapping draft、validation entry contract
- 后续可进入 implementation planning，而不是再次回到模糊探索

---

## 一句话结论

> 这个双轨子项目的核心不是继续“更努力地找”，而是用一次短、硬、可判定的 discovery 关口，把问题从“也许还有候选”尽快推进到“确认有候选”或“正式进入供给规格化”，从而为真实 3-agent 清掉当前最关键的上游供给阻塞。