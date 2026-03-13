from __future__ import annotations


def project_task_to_feishu_record(
    task: dict[str, object],
    *,
    executing_timeout_sec: int,
    reviewing_timeout_sec: int,
    blocked_alert_after_sec: int,
    now_ts: int,
    state_entered_ts: int | None = None,
    updated_at_ts: int | None = None,
    block_since_ts: int | None = None,
) -> dict[str, object]:
    if state_entered_ts is None:
        state_entered_ts = updated_at_ts if updated_at_ts is not None else now_ts

    state = str(task.get("state", ""))
    blocked = bool(task.get("blocked", 0))

    timeout_threshold = 0
    if state == "executing":
        timeout_threshold = executing_timeout_sec
    elif state == "reviewing":
        timeout_threshold = reviewing_timeout_sec

    timed_out = timeout_threshold > 0 and (now_ts - state_entered_ts) >= timeout_threshold
    block_alert = bool(
        blocked
        and block_since_ts is not None
        and blocked_alert_after_sec > 0
        and (now_ts - block_since_ts) >= blocked_alert_after_sec
    )

    return {
        "task_id": task.get("task_id"),
        "title": task.get("title"),
        "state": state,
        "current_role": task.get("current_role"),
        "priority": task.get("priority"),
        "risk_level": task.get("risk_level"),
        "blocked": blocked,
        "last_event_summary": task.get("last_event_summary"),
        "timed_out": timed_out,
        "block_alert": block_alert,
    }
