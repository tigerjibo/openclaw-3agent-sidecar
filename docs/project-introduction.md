# OpenClaw 3-Agent Sidecar 项目介绍

## 项目定位

`openclaw-3agent-sidecar` 是一个构建在官方 `openclaw/openclaw` 之上的 **3-agent 编排侧车（sidecar）**。

它不是 OpenClaw 的 fork，也不依赖修改官方 OpenClaw 源码。它的职责是把原本偏“单轮对话”的 agent runtime，升级为一套可持续推进、可审计、可恢复的制度化任务流。

核心三角色为：

- `coordinator`：任务归纳、目标澄清、验收标准定义
- `executor`：任务执行、产出与证据回填
- `reviewer`：独立审核、通过/驳回、进入 rework 或 done

对外宣传层可采用 **“明制小内阁”** 的角色表达：

- 皇帝：用户 / 下发任务的人
- 首辅：对应 `coordinator`，负责统筹、拆解、向皇帝负责
- 大学士：对应 `executor`，负责承办、执行、提交证据
- 监审官：对应 `reviewer`，负责独立审议、封驳返工、质量把关

需要特别注意：

- 这套“小内阁”叙事只用于 README、介绍页、演示与宣传文案
- 代码、API、测试、状态机、数据模型中的权威角色名仍然是 `coordinator / executor / reviewer`
- 不允许让外宣命名反向污染 runtime 抽象

## 为什么要独立成 sidecar

之所以拆成独立仓库，而不是继续放在旧 OpenClaw 工作区里推进，主要有四个原因：

1. **边界清晰**：官方 OpenClaw 负责 gateway / routing / agent runtime；sidecar 负责 task kernel / state machine / dispatch / recovery。
2. **降低耦合**：避免把任务状态机和制度流硬塞进 OpenClaw 内核逻辑，后面升级官方版本也更轻松。
3. **独立演进**：sidecar 可以单独开发、测试、回滚、部署。
4. **更利于交接**：新 agent 或新开发者只需要打开这个仓库，就能继续推进，不必在旧仓里翻历史包袱。

## 与官方 OpenClaw 的关系

### 官方 OpenClaw 负责

- gateway
- webhook / routing
- workspace / skills
- session / agent runtime

### sidecar 负责

- `tasks` / `task_events` 任务内核
- 3-agent 状态机
- dispatch / scheduler / recovery
- result 回写与审计事件
- projection / detail / metrics

### 明确边界

- 任务状态真相源在 sidecar，不在 OpenClaw session
- sidecar 不应修改官方 OpenClaw 核心源码
- OpenClaw 是运行底座，不是任务状态机本体

## 当前已经完成的能力

截至目前，新仓已经具备以下基础能力：

### 1. Task Kernel

- `tasks` 表
- `task_events` 表
- 状态机流转规则
- review / rework / block / unblock / cancel 基础操作

### 2. Adapter 最小闭环

- `ingress adapter`
  - 把制度化任务入口归一化并写入 task kernel
  - 基于 `request_id` 做幂等
- `agent invoke adapter`
  - 为 `coordinator / executor / reviewer` 生成稳定调用载荷
- `result adapter`
  - 消费结构化角色结果
  - 回写任务字段
  - 推进状态到 `queued / reviewing / rework / done`

### 3. Runtime 最小闭环

- `dispatcher`
  - 选择当前应执行角色
  - 标记 dispatch in-flight
  - 防止重复派发
- `scheduler`
  - 恢复重启前未完成的 dispatch
  - 扫描 ready task 并继续派发
- `recovery`
  - 释放错误残留的 in-flight dispatch
  - 识别 executing / reviewing timeout
  - 对 blocked 任务做最小 escalation 事件收口
- `agent health`
  - 输出角色级运行 / 停滞健康快照
  - 已接入服务健康面，区分“服务活着”和“角色是否卡住”

### 4. 基础控制面

- 本地 HTTP 服务骨架
- health / ready / metrics / detail / projection 基础能力
- 角色提示文件骨架（`roles/`）

## 当前未完成的能力

当前还没有完成的关键能力包括：

- `persistent DB path`
  - 当前 runner 仍以最小实现为主，需要切到真正持久化路径
- `recovery / health` 自动调度接线
  - 当前已具备基础能力，但还未由 scheduler / service runner 周期性驱动
- `production deployment scaffolding`
  - 生产部署脚手架和运维规范还未完全落定
- `真实 OpenClaw 对接`
  - 当前已经有 adapter contract 和最小本地闭环，但还未完成与真实官方 OpenClaw runtime 的完整接线

## 当前仓库结构

- `sidecar/`
  - 核心包
- `sidecar/adapters/`
  - ingress / invoke / result 适配层
- `sidecar/runtime/`
  - dispatcher / scheduler / 后续 recovery / health
- `sidecar/roles/`
  - 三角色与共享提示文件
- `docs/`
  - 架构、迁移说明、规划文档
- `tests/`
  - 最小闭环与运行时测试

## 当前验证状态

最近一次已验证通过：

- `pytest tests -q`
- `python -m compileall sidecar`

验证结果：

- `PYTEST_EXIT=0`
- `COMPILE_EXIT=0`

这说明截至当前交接时点：

- 现有最小 adapter/runtime 闭环是可运行的
- 不是只有文档，没有代码

同时也已经具备一批面向真实接线与运维的能力：

- OpenClaw hook 自动注册
- maintenance 驱动的注册重试
- hook 注册失败限频与下次重试时间
- 连续失败达到阈值时 health 降级与 readiness 阻断
- 面向值班场景的运维 runbook

## 推荐如何继续开发

如果要继续推进，推荐优先顺序是：

1. `service_runner.py` 持久化数据库路径
2. scheduler / service runner 接入周期性 recovery / health 驱动
3. 与真实 OpenClaw runtime 的 invoke/result 接线
4. production deployment 与运维面板
5. 轻量演示面与活动流可观测增强

如果是接手值班或上线准备，而不是继续开发，请先阅读 `docs/operations-runbook.md`。

## 一句话总结

> `openclaw-3agent-sidecar` 是一个独立于官方 OpenClaw 源码之外的 3-agent 制度化任务编排侧车。对外可讲成“明制小内阁”，对内则坚持 `coordinator / executor / reviewer` 的清晰抽象；当前已具备 task kernel、adapter、recovery、agent health 与基础 runtime 闭环，可继续向持久化、自动恢复与真实 OpenClaw 接线演进。
