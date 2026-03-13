# Edict Competitor Analysis

## Purpose

This document analyzes `cft0808/edict` as a reference competitor / adjacent product for `openclaw-3agent-sidecar`.

It is not written to copy the project wholesale.
Its purpose is to answer five questions:

1. What is Edict actually building?
2. Why is it compelling?
3. Where is it stronger than us today?
4. Where are we intentionally taking a different path?
5. What should we borrow, and what should we refuse to borrow?

---

## Executive summary

### Short conclusion

`edict` is best understood as a **highly productized, institution-themed OpenClaw collaboration system**.

Its strongest advantages are not simply “more agents”, but:

- strong narrative packaging
- institutional review as a product feature
- real-time dashboard and observability
- explicit authority matrix
- intervention and recovery workflows
- polished onboarding / demo experience

By contrast, `openclaw-3agent-sidecar` is currently stronger as a **clean orchestration kernel / sidecar runtime**:

- clearer source of truth
- lighter role model
- stricter separation from official OpenClaw core
- easier-to-test runtime boundaries
- better positioned to evolve as a reusable orchestration layer

### One-line judgment

> Edict is closer to a compelling product system; `openclaw-3agent-sidecar` is closer to a sustainable orchestration kernel.

That is a difference of **layer**, not simply a difference of maturity.

---

## What Edict is

## Product identity

Edict presents itself as a **三省六部 / imperial-governance-style multi-agent orchestration system** built on top of OpenClaw.

Its product story is extremely coherent:

- the user issues an imperial command
- a gatekeeping intake layer classifies whether the message is real work or casual chat
- planning, review, dispatch, execution, and reporting are institutionally separated
- all important progress is visible on a dashboard
- human intervention remains possible through stop / cancel / resume / approval operations

This is not just a framework API. It is a productized system with:

- roles
- dashboards
- templates
- examples
- Docker demo
- install script
- screenshots
- roadmap
- operating rhythm

## Core philosophy

Edict explicitly positions itself against “自由讨论式 multi-agent”.

Its argument is:

- free-form agent collaboration is hard to audit
- quality becomes opaque
- recovery is unclear
- human control is weak

Its counter-proposal is **制度化协作**:

- mandatory review
- authority boundaries
- status-machine-driven flow
- visible activities
- coordinated intervention

This philosophy is important because it overlaps with our own direction, even if the implementation layer is different.

---

## Edict’s strongest strengths

## 1. Narrative power

Edict’s biggest moat is probably narrative clarity.

It does not describe itself as “some agents plus workflow logic”.
It describes itself as a **political institution for AI coordination**.

That gives it:

- memorability
- differentiation
- demo friendliness
- strong visual identity
- easy social spread

This is a major lesson for us.

## 2. Institutional review as a product feature

Edict turns review from an optional human habit into a structural property.

The “门下省必审” idea is presented as a killer feature:

- planning cannot directly become execution
- review is not optional
- quality is not delegated to goodwill

This is strategically aligned with our own belief that execution and approval should not collapse into one role.

## 3. Observability is first-class

Edict is unusually strong in turning agent activity into a visible, interpretable stream.

Key capabilities include:

- status-based kanban
- department views
- activity timeline
- progress snapshots
- todo snapshots
- session JSONL fusion
- tool_result visibility
- agent online / heartbeat state
- resource tracking (tokens / cost / elapsed)
- stage durations

This makes the system feel operationally real rather than conceptually elegant but opaque.

## 4. Product completeness

Edict already has many “convince the user in 30 seconds” assets:

- Docker quick-start
- install script
- UI dashboard
- templates
- examples
- screenshots
- remote skill management
- roadmap and contribution guidance

This is a strong advantage over kernel-first projects.

## 5. Recovery story is concrete

Edict’s architecture docs present a richer operational story than many multi-agent products:

- stall detection
- retry
- escalation
- rollback
- approval / rejection loops
- authority violation handling

Even if some of this is tightly coupled to its own product model, the story itself is extremely compelling.

---

## Where Edict may be weaker or riskier

This section is important so we do not over-romanticize it.

## 1. Heavier role and product complexity

Edict is much larger in organizational scope:

- Taizi
- Zhongshu
- Menxia
- Shangshu
- multiple execution departments
- HR-like / news-like auxiliary roles

That gives it expressive power, but also increases:

- configuration weight
- maintenance burden
- onboarding complexity
- operational coupling

## 2. Business semantics are deeply embedded

Its states, roles, UI, scripts, and examples are heavily shaped by the 三省六部 metaphor.

That is great for product distinctiveness, but it makes the kernel less neutral.

By comparison, our runtime abstraction is currently cleaner:

- `coordinator`
- `executor`
- `reviewer`

This is easier to preserve as a reusable orchestration primitive.

## 3. Truth may be more distributed

Edict fuses multiple operational data sources:

- flow logs
- progress logs
- session JSONL
- dashboard views
- skill metadata
- agent status information

This is powerful for visibility, but it can also make “what exactly is canonical?” harder to answer.

Our project currently has an important structural advantage:

> task truth is explicitly meant to live in the sidecar kernel.

## 4. Product layer and runtime layer appear more tightly coupled

From the materials reviewed, Edict’s operational identity depends heavily on:

- scripts
- local data sync loops
- dashboard server
- session log interpretation
- front-end panels

That is fine for a product, but less ideal if the long-term goal is a clean orchestration substrate.

---

## Architecture comparison

## Edict

### Edict role model

A large institution with intake, planning, review, dispatch, multiple execution departments, HR-like administration, and information roles.

### Edict runtime style

Business-rich state machine plus dashboard-visible operational logic.

### Edict UX style

Highly visual, dashboard-first, template-rich.

### Edict operational style

Scripts, sync loops, dashboard APIs, skills management, agent activity fusion.

## `openclaw-3agent-sidecar`

### Sidecar role model

Three fixed canonical runtime roles:

- `coordinator`
- `executor`
- `reviewer`

Externally brandable as:

- 首辅
- 大学士
- 监审官

but only at the storytelling layer.

### Sidecar runtime style

Task kernel + adapter contracts + dispatch + scheduler + recovery + agent health.

### Sidecar UX style

Currently minimal control-plane / API / projection oriented.

### Sidecar operational style

Kernel-first, test-first, sidecar-first, low-coupling with official OpenClaw core.

---

## Direct comparison matrix

| Dimension | Edict | `openclaw-3agent-sidecar` |
| --- | --- | --- |
| Primary identity | Product system | Sidecar orchestration kernel |
| Role count | Large, institution-wide | Minimal 3-role core |
| Narrative strength | Very strong | Emerging, now stronger with 小内阁 framing |
| Review discipline | Strong and explicit | Strong via dedicated reviewer |
| Truth source clarity | Potentially more distributed | Intentionally centralized in sidecar |
| Observability | Very strong | Foundation exists, not yet productized |
| Recovery story | Rich product narrative | Early runtime implementation present |
| UI maturity | High | Low / early |
| Kernel neutrality | Lower | Higher |
| Ease of testing runtime | Lower / more coupled | Higher / cleaner boundaries |
| Risk of over-complexity | Higher | Lower |
| Demo wow factor | High | Currently moderate |

---

## What we should borrow

## 1. Borrow the storytelling discipline

Edict proves that product narrative matters.

We should not describe ourselves as:

- “three agents with a workflow”

We should describe ourselves as:

- a disciplined collaboration system
- a small cabinet
- a reviewable / recoverable / accountable delivery workflow

This is why our external framing now uses **明制小内阁**.

## 2. Borrow observability ambition

We should learn from Edict’s success in making agent work visible.

Not by copying all 10 panels, but by strengthening:

- task activity timeline
- event audit clarity
- detail views
- health / readiness visibility
- intervention history
- recovery outcomes

## 3. Borrow intervention ergonomics

Edict makes human intervention visible and actionable.

We should continue evolving toward clear operator controls such as:

- stop / resume
- cancel
- retry dispatch
- escalate blocked task
- inspect recovery actions

## 4. Borrow “review is structural” messaging

This is already aligned with our architecture.

We should keep emphasizing:

- execution does not self-certify completion
- review is independent
- approval / rejection is part of the orchestration contract

## 5. Borrow product packaging discipline

Edict’s strongest practical advantage is not only its architecture, but the completeness of its packaging.

We should gradually improve:

- top-of-README clarity
- demo narrative
- screenshots / diagrams later if useful
- operator documentation
- example workflows

---

## What we should not borrow

## 1. Do not copy the large bureaucracy shape

We should not turn our project into a 12-role system just because it looks impressive.

That would dilute the very thing that currently makes our architecture strong:

- small fixed role model
- clearer contracts
- lower runtime complexity
- easier testing and recovery reasoning

## 2. Do not replace canonical roles with branding terms in implementation

This is a hard line.

Even though we externally brand the system as a small cabinet:

- `coordinator`
- `executor`
- `reviewer`

must remain the canonical runtime roles.

## 3. Do not let observability replace truth

Activity streams, logs, projections, and UI are useful.
They must not become the new source of truth.

The sidecar kernel must remain the authoritative task state source.

## 4. Do not couple runtime progress to a heavyweight product shell too early

A beautiful dashboard is helpful, but if introduced too early it can distort architectural choices.

We should keep runtime evolution ahead of product shell complexity.

---

## Strategic interpretation for our project

Edict validates the market direction.

It demonstrates that there is real value in:

- role separation
- review-first collaboration
- recoverable task orchestration
- productized observability
- historical / institutional narrative framing

But our answer to the same space should be different.

### Our likely strategic path

- **Edict**: stronger as a full product experience today
- **Us**: stronger as a disciplined orchestration sidecar with cleaner kernel boundaries

So our differentiation should not be:

- “we also have historical institutions”

It should be:

- “we provide the smallest serious institution that still preserves accountability”
- “we do not need 12 roles to achieve discipline”
- “we prioritize a clean task truth source and runtime correctness”

---

## Recommended external messaging against heavier competitors

Use language like this:

> Some systems add more agents, more dashboards, and more ceremony. We take a smaller path: three roles with clear authority boundaries, a sidecar truth source, independent review, and recovery built into runtime behavior.

Chinese version:

> 有些系统通过增加角色、面板和流程仪式来变强；我们选择更小但更硬的路径：只保留三个关键角色，用清晰边界、独立审议、sidecar 真相源和内建恢复能力，保证 AI 协作真正可交付。

---

## Immediate product implications

### 1. Keep the small-cabinet framing

This is the right level of historical metaphor for us.

- not 12 departments
- not giant bureaucracy
- just enough institutional flavor to make the system memorable

### 2. Continue improving runtime before heavy UI

Current logical next priorities remain:

1. persistent DB path in `service_runner.py`
2. periodic recovery / health driving
3. stronger restart / stale / blocked regression coverage
4. real OpenClaw integration wiring

### 3. Strengthen documentation and product-facing explanation in parallel

We should continue building:

- brand positioning
- competitor analysis
- demo copy
- operator-oriented docs

That keeps the kernel-first path from becoming invisible.

---

## Final conclusion

Edict should not be treated as a template to clone.

It should be treated as proof that:

- institutional AI collaboration is legible to users
- review and accountability are product features
- observability can be a major differentiator
- narrative matters almost as much as architecture

Our job is to carry those lessons into a lighter, cleaner, more reusable sidecar runtime.

### Final one-line takeaway

> Edict shows how compelling a productized institutional system can be; `openclaw-3agent-sidecar` should answer with a smaller cabinet, a cleaner kernel, and stricter task truth discipline.
