from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(db_path: str | Path = ":memory:") -> sqlite3.Connection:
    path_text = str(db_path)
    if path_text != ":memory:":
        path_obj = Path(path_text)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path_text, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            task_type TEXT NOT NULL,
            source TEXT,
            raw_request TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            created_by TEXT,
            state TEXT NOT NULL DEFAULT 'inbox',
            current_role TEXT,
            priority TEXT NOT NULL DEFAULT 'normal',
            risk_level TEXT NOT NULL DEFAULT 'normal',
            requires_human_confirm INTEGER NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1,
            goal TEXT,
            acceptance_criteria TEXT,
            risk_notes TEXT,
            proposed_steps TEXT,
            review_round INTEGER NOT NULL DEFAULT 0,
            review_decision TEXT,
            review_comment TEXT,
            result_summary TEXT,
            evidence TEXT,
            open_issues TEXT,
            followup_notes TEXT,
            reasons TEXT,
            required_rework TEXT,
            residual_risk TEXT,
            last_invoke_id TEXT,
            dispatch_status TEXT NOT NULL DEFAULT 'idle',
            dispatch_role TEXT,
            dispatch_started_at TEXT,
            dispatch_attempts INTEGER NOT NULL DEFAULT 0,
            dispatch_error_kind TEXT,
            dispatch_error_status_code INTEGER,
            dispatch_error_retryable INTEGER NOT NULL DEFAULT 0,
            dispatch_error_message TEXT,
            rework_priority_available INTEGER NOT NULL DEFAULT 0,
            rework_priority_used INTEGER NOT NULL DEFAULT 0,
            blocked INTEGER NOT NULL DEFAULT 0,
            block_reason TEXT,
            block_since TEXT,
            waiting_on TEXT,
            last_event_at TEXT,
            last_event_summary TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS task_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT,
            action TEXT,
            summary TEXT,
            idempotency_key TEXT,
            trace_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(task_id) REFERENCES tasks(task_id)
        )
        """
    )

    _ensure_column(conn, "tasks", "dispatch_error_kind", "TEXT")
    _ensure_column(conn, "tasks", "dispatch_error_status_code", "INTEGER")
    _ensure_column(conn, "tasks", "dispatch_error_retryable", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "tasks", "dispatch_error_message", "TEXT")
    _ensure_column(conn, "task_events", "trace_id", "TEXT")

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_task_events_task_idempotency
        ON task_events(task_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
        """
    )

    conn.commit()


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def get_column_names(conn: sqlite3.Connection, table_name: str) -> list[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return [str(r[1]) for r in rows]


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str) -> None:
    if column_name in get_column_names(conn, table_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
