# Release Note Template

> 适用于 `openclaw-3agent-sidecar` 的一次版本发布、灰度切换、AWS staging 演练或线上热修复说明。

---

## 1. 发布概览

- **发布名称 / 批次：**
- **发布日期：**
- **发布负责人：**
- **变更分支 / 提交范围：**
- **目标环境：**
  - [ ] local
  - [ ] staging
  - [ ] production
- **发布类型：**
  - [ ] feature
  - [ ] fix
  - [ ] docs / runbook
  - [ ] operational change
  - [ ] rollback

### 一句话摘要

> 用 1~2 句话概括这次发布到底改了什么，以及为什么现在要发。

示例：

> 本次发布为 sidecar CLI bridge 增加按 `coordinator / executor / reviewer` 选择独立 OpenClaw agent 的能力，同时保留 `openclaw-cli://main` 的回退路径，降低后续多 agent 切换风险。

---

## 2. 本次变更

### 变更目标

- 这次要解决的问题：
- 对应计划 / issue / runbook：
- 是否涉及上游 OpenClaw 接线：
  - [ ] 是
  - [ ] 否

### 代码与配置改动

#### 代码改动

- （填写本次涉及的核心代码文件或模块）

#### 配置改动

- （填写新增、修改、删除的环境变量或部署参数）

#### 文档改动

- （填写本次补充或更新的文档 / runbook）

#### 数据库 / 持久化改动

- [ ] 无
- [ ] 有，说明如下：

### 对外行为变化

- **新增行为：**
- **保持兼容的旧行为：**
- **已知未覆盖范围：**

---

## 3. 风险点

### 技术风险

- [ ] runtime bridge 路由变化
- [ ] gateway hook 注册变化
- [ ] result callback 鉴权变化
- [ ] recovery / retry 行为变化
- [ ] SQLite / 持久化风险
- [ ] 仅文档风险

### 风险说明

- **最高风险点：**
- **触发条件：**
- **用户可见症状：**
- **值班观察点：**
  - `GET /healthz`
  - `GET /readyz`
  - `GET /ops/summary`
  - `openclaw-sidecar-remote-validate`

### 缓释措施

- （填写本次上线前后的保护措施）
- （例如灰度、回退开关、额外监控、人工盯盘）

---

## 4. 验证结果

### 本地 / CI 验证

- [ ] `pytest tests -q`
- [ ] `python -m compileall sidecar`

#### 关键定向测试

- （填写本次额外执行的定向测试文件或场景）

### 环境验证

- [ ] 未做环境验证
- [ ] 已做 staging 验证
- [ ] 已做 production 验证

### 验证记录

#### 命令 / 检查项

- （填写实际运行过的命令与检查项）

#### 结果摘要

- （填写通过 / 失败 / 部分通过的摘要）

#### 关键观测

- `integration.status =`
- `integration.runtime_invoke.bridge =`
- `integration.runtime_invoke.recent_submission =`
- `integration.probe =`

### 结论

- [ ] 可发布
- [ ] 可灰度
- [ ] 需人工盯盘
- [ ] 暂不建议发布

---

## 5. 发布步骤

1. 确认目标环境配置已就绪（特别是 `OPENCLAW_*` 相关变量）。
2. 部署代码或切换到目标提交。
3. 重启 sidecar 进程 / service。
4. 检查 `/healthz`、`/readyz`、`/ops/summary`。
5. 如涉及真实上游接线，运行 `openclaw-sidecar-remote-validate`。
6. 如需要真实闭环验证，运行 `openclaw-sidecar-remote-validate --dispatch-sample`。
7. 记录验证结果并决定继续放量或回滚。

---

## 6. 回滚方式

### 回滚触发条件

- （填写什么情况下必须立即回滚）
- （例如健康降级、callback 连续失败、关键闭环验证失败）

### 回滚步骤

1. 切回上一稳定提交 / 版本。
2. 恢复上一版环境变量或部署清单。
3. 重启 sidecar 服务。
4. 再次检查：
   - `GET /healthz`
   - `GET /readyz`
   - `GET /ops/summary`
5. 如涉及真实接线，再运行：
   - `openclaw-sidecar-remote-validate`

### 回滚后确认项

- `integration.status` 是否恢复预期
- `hook_registration.status` 是否恢复预期
- `runtime_invoke.recent_submission` 是否不再出现本次新增故障
- 是否需要人工解阻已进入 `blocked` 的任务

---

## 7. 值班备注

### 上线后重点盯盘时间窗

- **开始时间：**
- **结束时间：**
- **责任人：**

### 重点关注指标 / 字段

- `health.status`
- `readiness.status`
- `integration.gateway.hook_registration.status`
- `integration.runtime_invoke.result_callback_ready`
- `integration.runtime_invoke.recent_submission.last_submit_status`
- `integration.runtime_invoke.recent_submission.last_error_kind`

### 若出问题先看哪里

1. `blocking_issue_groups`
2. `ops.summary.integration.runtime_invoke.recent_submission`
3. `integration.probe.runtime_invoke`
4. sidecar / upstream runtime 日志

---

## 8. 对外沟通口径（可选）

### 面向内部开发 / 值班

> 本次发布已完成代码更新与基础验证，若出现异常，优先按 release note 中的回滚条件与 runbook 顺序处理，不要跳过 `ops/summary` 和 `remote_validate` 的结构化检查。

### 面向业务 / 非技术干系人

> 本次更新主要是对 sidecar 任务编排与上游接线稳定性的增强，发布后会持续观察关键健康与回调指标；如发现异常，可快速回退到上一稳定版本。
