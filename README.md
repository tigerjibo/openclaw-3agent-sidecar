# OpenClaw 3-Agent Sidecar

A lightweight 3-agent orchestration sidecar built on top of the official `openclaw/openclaw` runtime.

## Positioning

This repository is **not** an OpenClaw fork and does **not** modify official OpenClaw source code.

It acts as a sidecar orchestration layer that provides:

- task kernel (`tasks` + `task_events`)
- 3-agent state machine (`coordinator / executor / reviewer`)
- dispatch / review / rework flow
- projection / detail / metrics surfaces
- adapters for integrating with the official OpenClaw gateway

## Current scope

This initial migration carries over the reusable task-kernel foundation from the prototype implementation and establishes the independent repository skeleton.

Planned next layers:

- OpenClaw ingress adapter
- OpenClaw agent invoke adapter
- dispatcher / scheduler / recovery runtime
- role health tracking
- production deployment scaffolding

## Layout

- `sidecar/` — core package
- `sidecar/roles/` — shared and role-specific prompt files
- `docs/` — architecture and migration notes

## Environment

See `.env.example` and `.env` for the initial placeholder configuration.
