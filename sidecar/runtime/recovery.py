from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import contracts
from ..events import append_event
from ..metrics import get_state_entry_time
from ..models import get_task_by_id, get_task_trace_id, update_task_fields
from ..time_utils import ensure_utc, parse_utc_datetime, utc_now

_TERMINAL_STATES = {contracts.STATE_DONE, contracts.STATE_CANCELLED}


class TaskRecovery:
    def __init__(
        self,
        app,
        *,
        executing_timeout_sec: int = 3600,
        reviewing_timeout_sec: int = 3600,
        blocked_alert_after_sec: int = 3600,
    ) -> None:
        self.app = app
        self.executing_timeout_sec = int(executing_timeout_sec)
        self.reviewing_timeout_sec = int(reviewing_timeout_sec)
        self.blocked_alert_after_sec = int(blocked_alert_after_sec)

    def recover_inflight_dispatches(self) -> list[str]:
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
            self._release_dispatch(task_id, summary="recovery released inflight dispatch")
            append_event(
                self.app.conn,
                task_id=task_id,
                event_type="task.recovered",
                actor="recovery",
                action="recover_dispatch",
                summary="recovery released inflight dispatch",
                trace_id=trace_id,
            )
            recovered.append(task_id)
        self.app.conn.commit()
        return recovered

    def recover_execution_timeouts(self, *, now: datetime | None = None) -> list[str]:
        return self._recover_state_timeouts(
            state=contracts.STATE_EXECUTING,
            timeout_sec=self.executing_timeout_sec,
            now=now,
        )

    def recover_review_timeouts(self, *, now: datetime | None = None) -> list[str]:
        return self._recover_state_timeouts(
            state=contracts.STATE_REVIEWING,
            timeout_sec=self.reviewing_timeout_sec,
            now=now,
        )

    def recover_blocked_tasks(self, *, now: datetime | None = None) -> list[str]:
        current = ensure_utc(now) if now is not None else utc_now()
        rows = self.app.conn.execute(
            """
            SELECT task_id, blocked, block_since
            FROM tasks
            WHERE blocked = 1
              AND state NOT IN ('done', 'cancelled')
            ORDER BY created_at ASC, task_id ASC
            """
        ).fetchall()

        escalated: list[str] = []
        for row in rows:
            block_since = self._parse_datetime(row["block_since"])
            if block_since is None:
                continue
            if (current - block_since).total_seconds() <= self.blocked_alert_after_sec:
                continue

            task_id = str(row["task_id"])
            trace_id = get_task_trace_id(get_task_by_id(self.app.conn, task_id))
            self.app.conn.execute(
                "UPDATE tasks SET last_event_at = datetime('now'), last_event_summary = ? WHERE task_id = ?",
                ("recovery escalated blocked task", task_id),
            )
            append_event(
                self.app.conn,
                task_id=task_id,
                event_type="task.recovered",
                actor="recovery",
                action="escalate_blocked",
                summary="recovery escalated blocked task",
                trace_id=trace_id,
            )
            escalated.append(task_id)

        self.app.conn.commit()
        return escalated

    def run_once(self, *, now: datetime | None = None) -> dict[str, list[str]]:
        execution_timeout = self.recover_execution_timeouts(now=now)
        review_timeout = self.recover_review_timeouts(now=now)
        escalate_timeout = execution_timeout + [task_id for task_id in review_timeout if task_id not in execution_timeout]
        escalate_blocked = self.recover_blocked_tasks(now=now)
        retry_dispatch = self.recover_retryable_submit_failures()
        recover_dispatch = self.recover_inflight_dispatches()

        return {
            "recover_dispatch": recover_dispatch,
            "retry_dispatch": retry_dispatch,
            "escalate_timeout": escalate_timeout,
            "escalate_blocked": escalate_blocked,
        }

    def recover_retryable_submit_failures(self) -> list[str]:
        rows = self.app.conn.execute(
            """
                        SELECT task_id, dispatch_error_kind, dispatch_error_retryable FROM tasks
            WHERE dispatch_status = 'submit_failed'
              AND state NOT IN ('done', 'cancelled')
            ORDER BY created_at ASC, task_id ASC
            """
        ).fetchall()

        recovered: list[str] = []
        for row in rows:
            if not self._should_retry_submit_failure(kind=row["dispatch_error_kind"], retryable=row["dispatch_error_retryable"]):
                continue
            task_id = str(row["task_id"])
            trace_id = get_task_trace_id(get_task_by_id(self.app.conn, task_id))
            update_task_fields(
                self.app.conn,
                task_id,
                dispatch_status="idle",
                dispatch_role=None,
                dispatch_started_at=None,
            )
            self.app.conn.execute(
                "UPDATE tasks SET last_event_at = datetime('now'), last_event_summary = ? WHERE task_id = ?",
                ("recovery released retryable submit failure", task_id),
            )
            append_event(
                self.app.conn,
                task_id=task_id,
                event_type="task.recovered",
                actor="recovery",
                action="retry_dispatch",
                summary="recovery released retryable submit failure",
                trace_id=trace_id,
            )
            recovered.append(task_id)
        self.app.conn.commit()
        return recovered

    def _should_retry_submit_failure(self, *, kind: Any, retryable: Any) -> bool:
        if int(retryable or 0) != 1:
            return False
        return str(kind or "").strip() != "configuration_error"

    def _recover_state_timeouts(
        self,
        *,
        state: str,
        timeout_sec: int,
        now: datetime | None,
    ) -> list[str]:
        current = ensure_utc(now) if now is not None else utc_now()
        rows = self.app.conn.execute(
            """
            SELECT task_id, dispatch_status, dispatch_started_at
            FROM tasks
            WHERE state = ?
              AND state NOT IN ('done', 'cancelled')
            ORDER BY created_at ASC, task_id ASC
            """,
            (state,),
        ).fetchall()

        recovered: list[str] = []
        for row in rows:
            task_id = str(row["task_id"])
            trace_id = get_task_trace_id(get_task_by_id(self.app.conn, task_id))
            started_at = self._parse_datetime(row["dispatch_started_at"])
            if started_at is None:
                started_at = get_state_entry_time(self.app.conn, task_id, state)
            if started_at is None:
                continue
            if (current - started_at).total_seconds() <= timeout_sec:
                continue

            self._release_dispatch(task_id, summary=f"recovery timeout in state {state}")
            append_event(
                self.app.conn,
                task_id=task_id,
                event_type="task.recovered",
                actor="recovery",
                action="escalate_timeout",
                summary=f"recovery timeout in state {state}",
                trace_id=trace_id,
            )
            recovered.append(task_id)

        self.app.conn.commit()
        return recovered

    def _release_dispatch(self, task_id: str, *, summary: str) -> None:
        update_task_fields(
            self.app.conn,
            task_id,
            dispatch_status="idle",
            dispatch_role=None,
            dispatch_started_at=None,
        )
        self.app.conn.execute(
            "UPDATE tasks SET last_event_at = datetime('now'), last_event_summary = ? WHERE task_id = ?",
            (summary, task_id),
        )

    def _parse_datetime(self, value: Any) -> datetime | None:
        return parse_utc_datetime(value)
