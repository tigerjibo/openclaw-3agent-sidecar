# Real OpenClaw Integration Next Plan

**Goal:** 在已经完成 CLI bridge、HTTP invoke/result 最小闭环、reviewer-only AWS staging 验证的基础上，把 `openclaw-3agent-sidecar` 从“已证明可接通”推进到“真实 OpenClaw 接线边界清楚、契约稳定、可继续 staged rollout”的下一阶段。

**Scope:** 本计划只覆盖 sidecar 与官方 OpenClaw 之间的真实 `ingress / invoke / result` 接线补强，不回退到修改官方 OpenClaw 核心源码，也不重新讨论角色故事包装。

---

## 当前真实状态（按代码 / 测试 / staging 验证）

目前已经明确具备：

- `AgentInvokeAdapter` 已生成稳定 invoke 载荷：
  - `invoke_id`
  - `task_id`
  - `role`
  - `agent_id`
  - `trace_id`
  - `session_key`
  - `goal`
  - `input`
  - `constraints`
- `HttpOpenClawRuntimeBridge` 已支持在 invoke payload 中注入：
  - `callbacks.result.url`
  - `callbacks.result.headers.X-OpenClaw-Hooks-Token`
- `CliOpenClawRuntimeBridge` 已支持：
  - `openclaw agent --agent <id> --json`
  - role-specific agent routing
  - 结构化 callback failure 分类
  - late failure ignored 语义
- `LocalTaskKernelHttpService` 已暴露：
  - `POST /runtime/ingress`
  - `POST /runtime/result`
  - `POST /hooks/openclaw/ingress`
  - `POST /hooks/openclaw/result`
- `tests/test_openclaw_runtime_integration.py` 已覆盖：
  - HTTP invoke payload
  - result callback contract 注入
  - hook token 鉴权
  - HTTP 最小闭环
  - late failure ignored
- AWS staging 已验证：
  - CLI bridge 可用
  - reviewer-only role-specific routing 可用
  - `reviewer -> sysarch` 真正进入远端 OpenClaw 会话

因此，下一阶段不是“从零接线”，而是把已经存在但分散的契约、测试和运维语义收紧成一套更稳定的真实集成边界。

---

## 当前主要缺口

### 1. 契约文档仍偏摘要，不足以作为真实接线规范

`docs/adapter-contract.md` 目前只描述了高层摘要：

- ingress
- invoke
- result

但还缺少对以下内容的明确规范：

- `AgentInvokeAdapter.build_invoke()` 的完整字段约束
- `callbacks.result` 的必填 / 可选语义
- hook token 的来源优先级与鉴权规则
- `status=succeeded|failed` 时 result payload 的最小字段要求
- `result_error_kind` / `submission_error_kind` 的运维语义
- late failure ignored 的判断边界

### 2. ingress / result 的“真实上游语义”仍不够收紧

虽然入口和回写端点已经存在，但还应进一步明确：

- 哪些字段是 sidecar 必填
- 哪些字段允许上游缺省
- request_id / trace_id 的来源与继承规则
- 重复 ingress / 重复 result 的幂等边界
- callback 延迟到达时的接受/拒绝规则

### 3. 测试覆盖了最小闭环，但还缺更贴近真实接线的异常矩阵

还值得补的真实接线测试包括：

- 重复 callback 对不同任务状态的影响
- callback 先成功、submit 后失败之外的更多竞态顺序
- callback payload 缺少关键字段时的拒绝行为
- 非法 role / invoke_id / trace_id 组合的处理
- 上游返回结构正确但业务内容空洞时的 contract 判定

### 4. staging rollout 仍停留在 reviewer-only

当前真实环境已证明 reviewer-only 方案可用，但还缺：

- coordinator 独立 agent 验证
- executor 独立 agent 验证
- 更清晰的 staged rollout 进入/退出条件
- 每一阶段的回退检查表

### 5. 部署方式仍偏手工

远端部署目录不是 git 仓库，当前仍依赖人工归档/同步。

需要更稳定的：

- 打包与同步步骤
- 保留 `.env` / `.venv` / `data/` / `logs/` 的约定
- 重启后健康检查
- 失败回滚说明

---

## 下一阶段建议任务

### Task 1：扩写真实 adapter contract

**Files:**

- Modify: `docs/adapter-contract.md`
- If needed: `README.md`
- If needed: `docs/operations-runbook.md`

**目标：** 把当前代码中已经成立的真实 contract 写成可执行文档，而不是停留在摘要层。

应至少明确：

1. ingress payload 最小字段
2. invoke payload 的完整字段说明
3. `callbacks.result` 的注入规则
4. runtime / hook 两类 result 入口的鉴权与差异
5. `status=failed` 时允许的错误载荷
6. duplicate / late callback 的处理原则

### Task 2：补强真实接线异常矩阵测试

**Files:**

- Modify: `tests/test_openclaw_runtime_integration.py`
- If needed: `tests/test_result_concurrency.py`
- If needed: `tests/test_remote_validate.py`

**目标：** 把当前最小闭环测试扩展成“值班时遇到异常也有证据”的集成测试矩阵。

优先补：

1. callback payload 缺字段
2. callback role 与 invoke role 不匹配
3. 非法 / 过期 invoke_id
4. 重复 callback 幂等
5. submit 成功但 callback 鉴权失败
6. probe-only 与 dispatch-sample 的 blocker 输出一致性

### Task 3：梳理真实 ingress 来源约束

**Files:**

- Modify: `docs/adapter-contract.md`
- If needed: `sidecar/adapters/ingress.py`
- If needed: `tests/test_ingress_adapter.py`

**目标：** 把“谁能把制度化任务送进 sidecar”这件事写清楚。

至少要确认：

- `source=openclaw` 与其他来源的区分
- `request_id` 的幂等要求
- `trace_id` 是否允许上游提供并如何落库
- ingress hook 与 runtime ingress 的使用边界

### Task 4：继续推进 role-specific staging rollout

**Files:**

- New/Modify docs under `deploy/`
- New/Modify validation notes under `docs/plans/`

**目标：** 从 reviewer-only 继续小步放量。

建议顺序：

1. `coordinator + reviewer`
2. `executor + reviewer`
3. 三角色全量

每一步都保留：

- `ops/summary` 证据
- `recent_submission` 证据
- OpenClaw session 证据
- 回退到 `main` 的可验证路径

### Task 5：部署自动化最小收口

**Files:**

- New helper docs/scripts under `deploy/`
- Modify: `deploy/README.md`
- If needed: `docs/operations-runbook.md`

**目标：** 把当前手工 SSH + 归档同步流程收口成可重复操作。

至少要覆盖：

- 本地打包
- 远端同步
- 保留运行态目录
- 服务重启
- `healthz` / `readyz` / `ops/summary` 校验
- 回滚提示

---

## 推荐执行顺序

建议按下面顺序推进：

1. **Task 1：扩写真实 adapter contract**
2. **Task 2：补强真实接线异常矩阵测试**
3. **Task 4：继续推进 role-specific staging rollout**
4. **Task 5：部署自动化最小收口**
5. **Task 3：真实 ingress 来源约束补强**

原因：

- 先把 contract 写清楚，避免测试和环境验证各说各话
- 再用测试固定异常语义，防止 staging 放量时才发现边界漂移
- reviewer-only 已通过，继续放量能最快换来真实信心
- 部署自动化越早补，后续每次验证成本越低

---

## 验收标准

完成本计划的第一轮后，应至少满足：

1. `docs/adapter-contract.md` 足以描述真实 ingress / invoke / result 接线边界
2. 集成测试覆盖最小闭环之外的关键异常场景
3. 新增一轮非 reviewer-only 的 role-specific staging 验证记录
4. 部署文档可指导一次可重复的远端同步与健康检查
5. 以下验证命令继续稳定通过：
   - `pytest tests -q`
   - `python -m compileall sidecar`

---

## 一句话判断

> 当前阶段的重点，不是证明 sidecar “能不能接 OpenClaw”，而是把已经接通的真实链路收束成稳定 contract、异常矩阵和 staged rollout 方法论。
