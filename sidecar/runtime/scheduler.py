from __future__ import annotations

from typing import Any

from ..events import append_event
from ..models import get_task_by_id, get_task_trace_id, update_task_fields
from .dispatcher import TaskDispatcher

_TERMINAL_STATES = {"done", "cancelled"}


class TaskScheduler:
    def __init__(self, app, *, dispatcher: TaskDispatcher) -> None:
        self.app = app
        self.dispatcher = dispatcher

    def recover_inflight_tasks(self) -> list[str]:
        rows = self.app.conn.execute(
            """
            SELECT task_id FROM tasks
            WHERE dispatch_status = 'running'
              AND state NOT IN ('done', 'cancelled')
            ORDER BY created_at ASC, task_id ASC
            """
        ).fetchall()
        recovered: list[str] = []
        for row in rows:
            task_id = str(row["task_id"])
            trace_id = get_task_trace_id(get_task_by_id(self.app.conn, task_id))
            update_task_fields(self.app.conn, task_id, dispatch_status="idle", dispatch_role=None, dispatch_started_at=None)
            self.app.conn.execute(
                "UPDATE tasks SET last_event_at = datetime('now'), last_event_summary = ? WHERE task_id = ?",
                ("scheduler recovered inflight dispatch", task_id),
            )
            append_event(
                self.app.conn,
                task_id=task_id,
                event_type="task.recovered",
                actor="scheduler",
                action="recover_inflight",
                summary="scheduler recovered inflight dispatch",
                trace_id=trace_id,
            )
            recovered.append(task_id)
        self.app.conn.commit()
        return recovered

    def dispatch_ready_tasks(self, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.app.conn.execute(
            """
            SELECT task_id FROM tasks
            WHERE blocked = 0
              AND current_role IS NOT NULL
              AND state NOT IN ('done', 'cancelled')
                            AND (
                                        dispatch_status = 'idle'
                                 OR dispatch_status IS NULL
                            )
            ORDER BY created_at ASC, task_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        dispatched: list[dict[str, Any]] = []
        for row in rows:
            result = self.dispatcher.dispatch_task(str(row["task_id"]))
            if result.get("dispatched"):
                dispatched.append(result)
        return dispatched