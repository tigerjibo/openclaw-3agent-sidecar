# Real 3-Agent Target Plan

> 记录日期：2026-03-15
>
> 目标：把 `openclaw-3agent-sidecar` 从“3 角色 sidecar + reviewer-only role-specific routing”推进到“真实、可验证、可回滚的 3-agent staging / production rollout”。

---

## 1. 为什么要单独定义这份计划

当前系统已经具备：

- 固定三角色状态机：`coordinator / executor / reviewer`
- sidecar 侧任务真相源
- CLI bridge 与 result callback 闭环
- reviewer-only AWS staging 验证

但这还不等于真正的 3-agent。

截至 2026-03-15，AWS staging 的真实状态是：

- `reviewer -> sysarch`
- `coordinator -> main`（fallback）
- `executor -> main`（fallback）

因此当前更准确的描述是：

- **3 角色 workflow 已成立**
- **reviewer-only role-specific routing 已成立**
- **真实 3-agent 尚未开始**

这份计划的作用，就是把“真正 3-agent”从一句口号拆成可落地的阶段、门槛、证据与回滚路径。

---

## 2. 真实 3-agent 的定义

只有满足以下条件，才应将系统标记为 **real 3-agent staging**：

1. `OPENCLAW_COORDINATOR_AGENT_ID` 已显式配置
2. `OPENCLAW_EXECUTOR_AGENT_ID` 已显式配置
3. `OPENCLAW_REVIEWER_AGENT_ID` 已显式配置
4. 三个角色都不再依赖 fallback `main`
5. 三个配置的 upstream agent 在目标主机上都真实存在且可调用
6. `remote_validate --dispatch-sample` 在完整映射下成功
7. `ops/summary` 能展示完整 role mapping
8. 上游 session / 日志能证明三次 invoke 分别进入预期 agent

### 更严格、也更推荐的生产定义

建议将真正 3-agent 的长期稳定形态定义为：

- `coordinator` 对应专用 planning agent
- `executor` 对应专用 execution agent
- `reviewer` 对应专用 review agent
- `main` 仅保留为回滚 / fallback 应急路径，不作为 steady-state 生产角色映射

换句话说，**真正的 3-agent 不只是三角色存在，而是三角色都有独立、稳定、可验证的上游执行落点。**

---

## 3. 目标架构设计

### 3.1 目标角色路由

期望最终达到以下映射：

- `coordinator -> <coordinator-agent-id>`
- `executor -> <executor-agent-id>`
- `reviewer -> <reviewer-agent-id>`
- `main` 不承载 steady-state 三角色中的任何一个，只用于：
  - 紧急回退
  - 早期 smoke / compatibility 验证
  - 运维故障切换

### 3.2 侧边车职责保持不变

真实 3-agent 目标下，sidecar 继续承担：

- 任务状态机真相源
- 调度与重试
- callback 契约校验
- health / maintenance / anomaly summary
- metrics / detail / audit trail

上游 OpenClaw agent 继续承担：

- 按角色消费 invoke
- 返回结构化 JSON result
- 通过 callback / result 入口回写结果

### 3.3 核心设计原则

1. **sidecar 不让出任务真相源**
2. **角色语义先于 agent 名称**
3. **role-specific routing 要可证明，不可猜测**
4. **任何阶段都必须可回退到 reviewer-only 或 single-agent fallback**
5. **staging 成功的定义必须以真实 dispatch sample 为准，而不是仅凭配置存在**

---

## 4. 进入真实 3-agent 之前的前置条件

### 4.1 上游 agent 资源前置条件

这是当前最现实的 blocker。

截至 2026-03-15，AWS 主机上可确认的 agent 只有：

- `main`
- `sysarch`

Phase 0 inventory execution is now complete for this evidence round. The result is:

- `NO-GO`
- blocker -> `upstream agent supply gap`
- report of record -> `docs/plans/2026-03-15-phase0-agent-inventory-report.md`

也就是说，当前 blocker 已从“需要先做 inventory 确认”收敛为“inventory 已执行，但仍未发现可进入 Phase 2 的 coordinator-grade / executor-grade 上游 agent 供给”。

The next dual-track follow-on is now also partially executed:

- Gate 1 discovery closure report -> `docs/plans/2026-03-15-upstream-candidate-discovery-gate-report.md`
- Gate 1 result -> `no additional candidate`
- active next step -> Gate 2 provisioning

Until a future rollout-grade candidate appears, the active source of truth for this blocker has expanded from the Phase 0 report to include the Gate 2 provisioning package:

- `docs/plans/2026-03-15-upstream-candidate-provisioning-package.md`

因此在继续推进前，必须先满足以下至少一项：

### Option A：发现现有但尚未登记的候选 agent

例如在目标环境中确认新的：

- planning-oriented agent
- execution-oriented agent

### Option B：新增 / provision 专用 agent

推荐最终至少具备：

- `coord-*` / `planner-*` 一类 agent
- `exec-*` / `worker-*` 一类 agent
- `review-*` / 当前 `sysarch` 一类 reviewer agent

### Option C：短期机制验证允许共享，但不得冒充真正 3-agent

如果为了验证路由机制，临时让两个角色共享同一个 agent，例如：

- `coordinator -> sysarch`
- `reviewer -> sysarch`

这可以作为**过渡性实验**，但它只能叫：

- role-specific routing expansion test
- dual-role mapping validation

而不能叫：

- real 3-agent
- full 3-agent rollout

### 4.2 sidecar 可观测性前置条件

在完整 3-agent 前，建议保证以下证据链稳定可取：

- `ops/summary.integration.runtime_invoke.bridge.role_agent_mapping`
- `ops/summary.integration.runtime_invoke.recent_submission`
- sidecar journal 中能看到选中的 agent / invoke 结果
- upstream session log 能按 agent 目录区分落点

如果其中任一证据链不稳定，先补观测，再放量。

### 4.3 契约稳定性前置条件

在完整 3-agent 前，result callback 契约至少要保证：

- `trace_id` 匹配校验
- active dispatch 的 `invoke_id` 匹配校验
- active dispatch 的 `role` 匹配校验
- duplicate callback 幂等
- unknown task / invalid role / missing field 明确报 `400 invalid_request`

截至当前，这部分基础已经明显加强，但后续仍可继续补 stale callback 语义与更多异常矩阵测试。

---

## 5. 阶段划分

### Phase 0 — 资源发现与命名收敛

#### Phase 0 目标

弄清楚真实 3-agent 所需的 upstream agent 是否存在、叫什么、谁负责维护。

#### Phase 0 要做什么

1. 在 AWS / upstream 环境确认候选 agent 列表
2. 给三类 agent 建议明确命名
3. 明确哪些 agent 可用于：
   - planning
   - execution
   - review
4. 明确 `main` 是否退出 steady-state 角色映射

#### Phase 0 退出标准

至少拿到一份明确映射草案：

- `coordinator -> <candidate>`
- `executor -> <candidate>`
- `reviewer -> <candidate>`

如果 Phase 0 没完成，后续所有所谓 3-agent rollout 都只是空转。

---

### Phase 1 — reviewer-only 基线固化

#### Phase 1 当前状态

已完成。

#### Phase 1 目标

把 reviewer-only 作为以后所有回退路径与比对基线。

#### Phase 1 应保留的证据

- `.env` baseline 示例
- rollout checklist
- staging validation note
- `ops/summary` 证据
- upstream `sysarch` session 证据

#### Phase 1 退出标准

reviewer-only 基线可随时恢复、随时复测。

---

### Phase 2 — coordinator 扩展验证

#### Phase 2 目标

在不改 executor 的情况下，验证 `coordinator` 能稳定切换到专用 agent。

#### Phase 2 推荐配置

- `OPENCLAW_COORDINATOR_AGENT_ID=<real-coordinator-agent-id>`
- `OPENCLAW_EXECUTOR_AGENT_ID=`
- `OPENCLAW_REVIEWER_AGENT_ID=<real-reviewer-agent-id>`

#### Phase 2 要验证什么

1. planner 输出结构是否稳定
2. `goal / acceptance_criteria / proposed_steps` 是否质量稳定
3. callback 闭环是否保持成功
4. `ops.summary.integration.runtime_invoke.recent_submission` 是否反映正确路由

#### Phase 2 风险

- coordinator agent 的 JSON 输出契约不稳定
- coordinator 改为专用 agent 后，调度推进节奏发生漂移

#### Phase 2 退出标准

连续多次 dispatch sample 成功，且 reviewer-only 基线可快速回退。

---

### Phase 3 — executor 扩展验证

#### Phase 3 目标

在 coordinator / reviewer 已稳定后，验证 `executor` 切换到专用 agent。

#### Phase 3 推荐配置

- `OPENCLAW_COORDINATOR_AGENT_ID=<real-coordinator-agent-id>`
- `OPENCLAW_EXECUTOR_AGENT_ID=<real-executor-agent-id>`
- `OPENCLAW_REVIEWER_AGENT_ID=<real-reviewer-agent-id>`

#### Phase 3 要验证什么

1. executor 输出结构是否满足 sidecar 契约
2. `result_summary / evidence / open_issues / followup_notes` 是否稳定
3. callback 成功率是否下降
4. sidecar recovery 是否出现新的 submit_failed / blocked pattern

#### Phase 3 风险

- executor agent 的执行时间或 JSON 质量不稳定
- executor 与 reviewer 之间的质量冲突增大
- callback 成功但业务内容空洞，导致“技术成功、交付失败”

#### Phase 3 退出标准

executor 切换后，真实 dispatch sample 与小样本真实任务均成功，且无持续 submit_failed 循环。

---

### Phase 4 — real 3-agent staging

#### Phase 4 目标

在 AWS staging 上达到真正的完整 3-agent 形态，并用真实证据证明。

#### Phase 4 核心验收项

- 三个角色都有显式 agent id
- 无角色依赖 fallback `main`
- 完整 dispatch sample 成功
- `ops/summary` 呈现完整 mapping
- upstream session 证据齐全
- 回滚流程已演练

#### Phase 4 产出物

- staging validation note（full 3-agent）
- rollout checklist 更新
- `.env` full-3-agent baseline 示例
- release note / handoff 更新

---

### Phase 5 — production 3-agent rollout

#### Phase 5 目标

把 staging 已验证的完整 3-agent 形态迁移到正式环境。

#### Phase 5 额外要求

1. 部署自动化至少半自动化
2. 回滚步骤已固化
3. 健康与 readiness 报警门槛明确
4. 运维知道如何识别：
   - callback 问题
   - agent 缺失
   - submit failure
   - result contract drift

#### Phase 5 退出标准

生产环境完整 3-agent 运行稳定，并具备标准运维剧本。

---

## 6. 推荐后续任务清单

### Track A：上游 agent 发现 / 供给

这是当前第一优先级。

1. 明确 upstream agent inventory 来源
2. 确认是否存在 coordinator / executor 候选
3. 若不存在，协调新增专用 agent
4. 明确 agent 命名规范与职责归属

### Track B：sidecar 路由与观测增强

1. 保证 `selected_agent_id` 证据稳定输出
2. 保证 `recent_submission` 能快速读懂路由结果
3. 需要时补充 role -> selected_agent 的直接摘要
4. 继续补 callback / stale / race 异常矩阵测试

### Track C：staging rollout 执行

1. reviewer-only 基线长期保留
2. coordinator 扩展验证
3. executor 扩展验证
4. full 3-agent staging 记录

### Track D：部署与运维硬化

1. 固化远端同步流程
2. 固化健康检查脚本
3. 固化回滚模板
4. 固化 full 3-agent 的 baseline env 示例

---

## 7. 未来两周建议顺序

### Week 1

1. 完成 upstream agent inventory 确认
2. 明确 coordinator / executor 候选或新增需求
3. 若候选存在，做 coordinator 扩展验证
4. 继续补 1~2 个 callback / stale 语义测试

### Week 2

1. 做 executor 扩展验证
2. 整理 full 3-agent staging checklist
3. 产出 full 3-agent baseline env 示例
4. 视结果决定是否进入 production rollout 准备

如果 Week 1 结束时仍拿不到 executor / coordinator 候选，则不要假装进入 3-agent；应明确回报 blocker 是**上游 agent 供给不足**。

---

## 8. 成功与失败的判定

### 成功信号

- 角色映射清晰且证据充足
- 完整闭环稳定
- 无持续 fallback 依赖
- 无反复 callback / submit 异常
- 可以快速回退

### 失败信号

- 只有配置，没有真实 sample 成功
- 两个角色共享一个 agent 却被误称为 3-agent
- 仍依赖 `main` fallback 却宣称 full rollout
- 出现 contract drift 但没有测试先发现
- 运维无法从 `ops/summary` 快速判断问题落在哪个角色

---

## 9. 当前最务实的一句话结论

> 真正的 3-agent 不是再多写几条环境变量，而是先拿到三类可用 upstream agent，再通过 staged rollout、真实 sample dispatch、ops 证据与回滚能力，把三角色映射从“存在”推进到“可信”。
