from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Optional

from sidecar import contracts


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    task_type: str
    state: str = contracts.STATE_INBOX
    current_role: str = "coordinator"
    priority: str = "normal"
    risk_level: str = "normal"
    requires_human_confirm: bool = False
    source: Optional[str] = None
    created_by: Optional[str] = None
    raw_request: Optional[str] = None
    metadata_json: Optional[str] = None


def create_task(conn: sqlite3.Connection, task: Task) -> None:
    conn.execute(
        """
        INSERT INTO tasks (
            task_id, title, task_type, source, raw_request, metadata_json, created_by,
            state, current_role, priority, risk_level, requires_human_confirm
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.task_id,
            task.title,
            task.task_type,
            task.source,
            task.raw_request,
            task.metadata_json,
            task.created_by,
            task.state,
            task.current_role,
            task.priority,
            task.risk_level,
            int(task.requires_human_confirm),
        ),
    )


def get_task_by_id(conn: sqlite3.Connection, task_id: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    return dict(row) if row else None


def list_tasks(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC, task_id DESC").fetchall()
    return [dict(r) for r in rows]


def update_task_fields(conn: sqlite3.Connection, task_id: str, **fields: object) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = [json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for value in fields.values()]
    conn.execute(
        f"UPDATE tasks SET {assignments}, updated_at = datetime('now') WHERE task_id = ?",
        (*values, task_id),
    )


def mark_task_blocked(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    reason: str,
    waiting_on: Optional[str] = None,
) -> None:
    conn.execute(
        """
        UPDATE tasks
        SET blocked = 1,
            block_reason = ?,
            waiting_on = ?,
            block_since = datetime('now'),
            updated_at = datetime('now')
        WHERE task_id = ?
        """,
        (reason, waiting_on, task_id),
    )


def clear_task_blocked(conn: sqlite3.Connection, task_id: str) -> None:
    conn.execute(
        """
        UPDATE tasks
        SET blocked = 0,
            block_reason = NULL,
            waiting_on = NULL,
            block_since = NULL,
            updated_at = datetime('now')
        WHERE task_id = ?
        """,
        (task_id,),
    )
