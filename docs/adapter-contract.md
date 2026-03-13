# Adapter Contract Summary

This repository follows a three-step contract between official OpenClaw and the sidecar.

## 1. Ingress

OpenClaw sends institutional tasks into the sidecar using a normalized ingress payload.

## 2. Invoke

The sidecar invokes one of the three role agents:

- coordinator
- executor
- reviewer

Each invocation must carry a stable `invoke_id`, `task_id`, `role`, `agent_id`, and structured input.

## 3. Result

Agent output is returned as structured data and written back into the task kernel.

The full draft remains documented in the original planning documents and should be copied/refined as the next migration step.
