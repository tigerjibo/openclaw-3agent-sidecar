from __future__ import annotations

import sqlite3
from typing import Optional


def append_event(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    event_type: str,
    actor: Optional[str],
    action: Optional[str],
    summary: str,
    idempotency_key: Optional[str] = None,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO task_events (
            task_id, event_type, actor, action, summary, idempotency_key
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, event_type, actor, action, summary, idempotency_key),
    )
    lastrowid = cur.lastrowid
    if lastrowid is None:
        raise RuntimeError("failed to retrieve lastrowid for appended event")
    return int(lastrowid)


def list_recent_events(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    limit: int = 20,
) -> list[dict]:
    rows = conn.execute(
        """
        SELECT id, task_id, event_type, actor, action, summary, idempotency_key, created_at
        FROM task_events
        WHERE task_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (task_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]
