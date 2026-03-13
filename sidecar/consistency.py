from __future__ import annotations

from typing import Any

from sidecar import contracts

_REQUIRED_FIELDS = ("task_id", "title", "state", "current_role")


def check_projection_consistency(
    task: dict[str, Any],
    *,
    projection: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for field in _REQUIRED_FIELDS:
        val = task.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            issues.append({
                "category": "missing_field",
                "reason": f"required field '{field}' is missing or empty",
            })

    if projection is None:
        return issues

    if projection.get("task_id") != task.get("task_id"):
        issues.append({
            "category": "projection_mismatch",
            "reason": "projection task_id does not match task kernel task_id",
        })

    if bool(projection.get("timed_out")):
        state = str(task.get("state") or "")
        if state == contracts.STATE_EXECUTING:
            issues.append({
                "category": contracts.ANOMALY_EXECUTION_TIMEOUT,
                "reason": "task exceeded executing timeout threshold",
            })
        elif state == contracts.STATE_REVIEWING:
            issues.append({
                "category": contracts.ANOMALY_REVIEW_TIMEOUT,
                "reason": "task exceeded reviewing timeout threshold",
            })

    if bool(projection.get("block_alert")):
        issues.append({
            "category": contracts.ANOMALY_BLOCKED,
            "reason": "task has remained blocked beyond alert threshold",
        })

    if task.get("state") == contracts.STATE_REVIEWING and bool(task.get("requires_human_confirm")):
        issues.append({
            "category": contracts.ANOMALY_PENDING_HUMAN_CONFIRM,
            "reason": "task is waiting for required human confirmation",
        })

    return issues
