# Brand Positioning Draft

## Purpose

This document defines the outward-facing product messaging for `openclaw-3agent-sidecar`.

It is intentionally separate from the runtime architecture documents.

- **Product communication layer** may use historical / narrative framing.
- **Runtime implementation layer** must keep canonical role ids and technical truth.

## Core positioning

### English

`openclaw-3agent-sidecar` is a lightweight 3-agent orchestration sidecar for OpenClaw.
It turns AI collaboration from free-form conversation into a disciplined workflow with planning, execution, review, recovery, and observability.

### 中文

`openclaw-3agent-sidecar` 是一个基于 OpenClaw 的轻量 3-Agent 编排侧车。
它不是让多个 Agent 自由聊天，而是把 AI 协作组织成一个可规划、可执行、可审议、可恢复、可审计的制度化流程。

## Narrative framing

### Recommended external metaphor

明制小内阁 3-Agent 协作系统

### Role mapping

- 皇帝：用户 / 任务发起者
- 首辅：对应 `coordinator`，负责统筹、拆解、推进、向皇帝负责
- 大学士：对应 `executor`，负责承办、执行、提交成果与证据
- 监审官：对应 `reviewer`，负责独立审议、封驳返工、质量把关

### Mandatory boundary

The historical framing is for README, demos, product decks, public communication, and onboarding narratives.

It must **not** replace the internal source of truth in:

- code
- tests
- APIs
- database fields
- state machines
- event types

Canonical runtime roles remain:

- `coordinator`
- `executor`
- `reviewer`

## What makes us different

### Short answer

Not more agents. Better separation of responsibility.

### Expanded answer

Most multi-agent systems fall into one of two traps:

1. too much freedom — agents talk, but ownership becomes blurry
2. too much structure — the system becomes heavy before it becomes useful

This project takes a narrower path:

- exactly 3 roles
- clear authority boundaries
- review independent from execution
- sidecar task truth source
- recovery and health built into runtime responsibilities

## Messaging pillars

### 1. 轻量但不是简陋

We should present the system as intentionally compact, not incomplete.

Suggested expression:

> 小内阁，不是小打小闹，而是用最小必要分工保证交付质量。

### 2. 制度化而不是群聊化

Suggested expression:

> 我们不让一群 AI 自己开会，而是让三个角色各司其职。

### 3. 可恢复、可审计、可干预

Suggested expression:

> 任务卡住了能恢复，执行有问题能驳回，状态变化有审计链路。

### 4. Sidecar 化而不是侵入式改造

Suggested expression:

> 不改官方 OpenClaw 核心，而是在其之上构建独立编排层。

## Slogan candidates

### Chinese

- **小内阁，大协作。**
- **三角制衡，让 AI 协作真正可交付。**
- **不是 Agent 越多越强，而是分工越清楚越可靠。**
- **首辅统筹，大学士承办，监审官把关。**

### English slogans

- **Small Cabinet, Serious Delivery.**
- **Three roles. Clear accountability.**
- **Less chatter. More delivery discipline.**
- **Plan. Execute. Review. Recover.**

## README top-copy draft

### Chinese-facing version

> 一个基于 OpenClaw 的轻量 3-Agent sidecar。对外可讲成“明制小内阁”：皇帝下旨，首辅统筹，大学士承办，监审官把关；对内则坚持 `coordinator / executor / reviewer` 的清晰抽象，把 AI 协作变成可审计、可恢复、可干预的交付流程。

### English-facing version

> A lightweight 3-agent sidecar for OpenClaw. Externally, it can be framed as a Ming-style small cabinet: the Emperor issues the task, the Chief Grand Secretary orchestrates, the Grand Secretary executes, and the Supervising Reviewer independently reviews. Internally, the runtime remains a clean `coordinator / executor / reviewer` system focused on recoverable, reviewable delivery.

## Differentiation template vs heavier competitors

Use when describing how this project differs from larger orchestration products:

> Some systems scale by adding more roles, more dashboards, and more ceremony. We scale by tightening responsibility boundaries around three essential roles: planning, execution, and review. The result is a lighter sidecar that is easier to reason about, easier to test, and easier to evolve.

## Do / Don't

### Do

- emphasize 3-role clarity
- emphasize review independence
- emphasize sidecar truth source
- emphasize recovery and observability
- use historical metaphor as a friendly entry point

### Don't

- imply the project is a fork of OpenClaw
- replace canonical role ids in technical docs
- over-promise a giant bureaucracy or 12-role system
- let branding language distort implementation boundaries

## Recommended next usage

This document can be used as the source for:

- README top section refinement
- homepage / landing page copy
- demo narration
- product deck intro
- repository description polish
