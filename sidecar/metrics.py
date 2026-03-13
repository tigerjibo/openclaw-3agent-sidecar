from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from .contracts import (
    ANOMALY_BLOCKED,
    ANOMALY_EXECUTION_TIMEOUT,
    ANOMALY_PENDING_HUMAN_CONFIRM,
    ANOMALY_REVIEW_TIMEOUT,
    EVENT_TASK_TRANSITIONED,
    STATE_EXECUTING,
    STATE_REVIEWING,
    TASK_STATES,
)


def get_state_entry_time(conn: sqlite3.Connection, task_id: str, state: str) -> datetime | None:
    row = conn.execute(
        """
        SELECT created_at FROM task_events
        WHERE task_id = ? AND event_type = ? AND summary LIKE ?
        ORDER BY id DESC LIMIT 1
        """,
        (task_id, EVENT_TASK_TRANSITIONED, f"% -> {state}"),
    ).fetchone()
    if row is None:
        return None
    return datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _get_timeout_reference_time(conn: sqlite3.Connection, task_id: str, state: str, dispatch_started_at: Any) -> datetime | None:
    started_at = _parse_datetime(dispatch_started_at)
    if started_at is not None:
        return started_at
    return get_state_entry_time(conn, task_id, state)


def compute_metrics_snapshot(
    conn: sqlite3.Connection,
    *,
    executing_timeout_sec: int,
    reviewing_timeout_sec: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.utcnow()
    state_counts: dict[str, int] = {s: 0 for s in TASK_STATES}
    for row in conn.execute("SELECT state, COUNT(*) as cnt FROM tasks GROUP BY state").fetchall():
        state_counts[row["state"]] = row["cnt"]

    blocked_count = conn.execute("SELECT COUNT(*) as cnt FROM tasks WHERE blocked = 1").fetchone()["cnt"]
    pending_hc = conn.execute(
        "SELECT COUNT(*) as cnt FROM tasks WHERE state = ? AND requires_human_confirm = 1",
        (STATE_REVIEWING,),
    ).fetchone()["cnt"]

    review_timeout_count = 0
    for row in conn.execute("SELECT task_id, dispatch_started_at FROM tasks WHERE state = ?", (STATE_REVIEWING,)).fetchall():
        entry_time = _get_timeout_reference_time(conn, row["task_id"], STATE_REVIEWING, row["dispatch_started_at"])
        if entry_time is not None and (now - entry_time).total_seconds() > reviewing_timeout_sec:
            review_timeout_count += 1

    execution_timeout_count = 0
    for row in conn.execute("SELECT task_id, dispatch_started_at FROM tasks WHERE state = ?", (STATE_EXECUTING,)).fetchall():
        entry_time = _get_timeout_reference_time(conn, row["task_id"], STATE_EXECUTING, row["dispatch_started_at"])
        if entry_time is not None and (now - entry_time).total_seconds() > executing_timeout_sec:
            execution_timeout_count += 1

    return {
        "state_counts": state_counts,
        "blocked_count": blocked_count,
        "pending_human_confirm_count": pending_hc,
        "review_timeout_count": review_timeout_count,
        "execution_timeout_count": execution_timeout_count,
    }


def compute_anomaly_summary(
    conn: sqlite3.Connection,
    *,
    executing_timeout_sec: int,
    reviewing_timeout_sec: int,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.utcnow()
    anomalies: list[dict[str, Any]] = []

    blocked_ids = [row["task_id"] for row in conn.execute("SELECT task_id FROM tasks WHERE blocked = 1").fetchall()]
    if blocked_ids:
        anomalies.append({"category": ANOMALY_BLOCKED, "task_ids": blocked_ids})

    review_timeout_ids = []
    for row in conn.execute("SELECT task_id, dispatch_started_at FROM tasks WHERE state = ?", (STATE_REVIEWING,)).fetchall():
        entry_time = _get_timeout_reference_time(conn, row["task_id"], STATE_REVIEWING, row["dispatch_started_at"])
        if entry_time is not None and (now - entry_time).total_seconds() > reviewing_timeout_sec:
            review_timeout_ids.append(row["task_id"])
    if review_timeout_ids:
        anomalies.append({"category": ANOMALY_REVIEW_TIMEOUT, "task_ids": review_timeout_ids})

    exec_timeout_ids = []
    for row in conn.execute("SELECT task_id, dispatch_started_at FROM tasks WHERE state = ?", (STATE_EXECUTING,)).fetchall():
        entry_time = _get_timeout_reference_time(conn, row["task_id"], STATE_EXECUTING, row["dispatch_started_at"])
        if entry_time is not None and (now - entry_time).total_seconds() > executing_timeout_sec:
            exec_timeout_ids.append(row["task_id"])
    if exec_timeout_ids:
        anomalies.append({"category": ANOMALY_EXECUTION_TIMEOUT, "task_ids": exec_timeout_ids})

    pending_hc_ids = [
        row["task_id"]
        for row in conn.execute(
            "SELECT task_id FROM tasks WHERE state = ? AND requires_human_confirm = 1",
            (STATE_REVIEWING,),
        ).fetchall()
    ]
    if pending_hc_ids:
        anomalies.append({"category": ANOMALY_PENDING_HUMAN_CONFIRM, "task_ids": pending_hc_ids})

    return anomalies
