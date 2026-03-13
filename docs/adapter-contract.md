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

For direct HTTP runtime integration, the invoke payload should also include a `callbacks.result` contract so the upstream runtime can post the structured role result back into the sidecar:

- `callbacks.result.url`
- `callbacks.result.headers.X-OpenClaw-Hooks-Token` (when hook auth is enabled)

This allows a real runtime submission to complete the minimal `invoke -> result` loop without relying on out-of-band callback configuration.

## 3. Result

Agent output is returned as structured data and written back into the task kernel.

The callback payload must echo:

- `invoke_id`
- `task_id`
- `role`
- `trace_id`
- `status`
- `output`

The full draft remains documented in the original planning documents and should be copied/refined as the next migration step.
