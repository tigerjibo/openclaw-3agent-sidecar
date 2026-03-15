from __future__ import annotations

import logging
from typing import Any

from ..adapters.agent_invoke import AgentInvokeAdapter
from ..adapters.openclaw_runtime import OpenClawRequestError, OpenClawRuntimeBridge
from ..api import TaskKernelApiApp
from ..events import append_event
from ..models import get_task_by_id, get_task_trace_id, update_task_fields

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {"done", "cancelled"}


class TaskDispatcher:
    def __init__(self, app: TaskKernelApiApp, *, runtime_bridge: OpenClawRuntimeBridge | None = None) -> None:
        self.app = app
        self.invoke_adapter = AgentInvokeAdapter(app)
        self.runtime_bridge = runtime_bridge

    def dispatch_task(self, task_id: str, *, force: bool = False) -> dict[str, Any]:
        task = get_task_by_id(self.app.conn, task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        if int(task.get("blocked") or 0) == 1:
            return {"dispatched": False, "reason": "blocked", "task_id": task_id}
        if str(task.get("state") or "") in _TERMINAL_STATES:
            return {"dispatched": False, "reason": "terminal", "task_id": task_id}

        role = str(task.get("current_role") or "").strip()
        if not role:
            return {"dispatched": False, "reason": "no_role", "task_id": task_id}

        if not force and str(task.get("dispatch_status") or "idle") == "running" and str(task.get("dispatch_role") or "") == role:
            return {"dispatched": False, "reason": "already_running", "task_id": task_id}

        invoke_payload = self.invoke_adapter.build_invoke(task_id, role=role)
        trace_id = str(invoke_payload.get("trace_id") or get_task_trace_id(task) or task_id)
        attempts = int(task.get("dispatch_attempts") or 0) + 1
        with self.app.conn:
            update_task_fields(
                self.app.conn,
                task_id,
                dispatch_status="running",
                dispatch_role=role,
                dispatch_started_at=self._now_expr_value(),
                dispatch_attempts=attempts,
                last_invoke_id=invoke_payload["invoke_id"],
                last_event_summary=f"dispatch {role}: {invoke_payload['invoke_id']}",
                dispatch_error_kind=None,
                dispatch_error_status_code=None,
                dispatch_error_retryable=0,
                dispatch_error_message=None,
            )
            self.app.conn.execute(
                "UPDATE tasks SET dispatch_started_at = datetime('now'), last_event_at = datetime('now') WHERE task_id = ?",
                (task_id,),
            )
            append_event(
                self.app.conn,
                task_id=task_id,
                event_type="task.dispatched",
                actor="dispatcher",
                action=role,
                summary=f"dispatch {role}: {invoke_payload['invoke_id']}",
                idempotency_key=f"dispatch:{invoke_payload['invoke_id']}",
                trace_id=trace_id,
            )

        runtime_submission = None
        submission_error = None
        submission_error_kind = None
        submission_status_code = None
        submission_retryable = False
        submission_error_details = None
        if self.runtime_bridge is not None:
            try:
                runtime_submission = self.runtime_bridge.submit_invoke(invoke_payload)
            except OpenClawRequestError as exc:
                logger.warning("Runtime submission failed for task=%s trace=%s kind=%s retryable=%s status=%s msg=%s", task_id, trace_id, exc.kind, exc.retryable, exc.status_code, exc)
                submission_error = str(exc)
                submission_error_kind = exc.kind
                submission_status_code = exc.status_code
                submission_retryable = bool(exc.retryable)
                submission_error_details = dict(exc.details or {})
            except Exception as exc:
                logger.warning("Runtime submission failed for task=%s trace=%s msg=%s", task_id, trace_id, exc)
                submission_error = str(exc)
                submission_error_kind = "unexpected_error"
                submission_retryable = False
        if submission_error is None:
            return {
                "dispatched": True,
                "task_id": task_id,
                "invoke_payload": invoke_payload,
                "runtime_submission": runtime_submission,
            }

        with self.app.conn:
            current = get_task_by_id(self.app.conn, task_id)
            if current is None:
                raise ValueError(f"task not found: {task_id}")

            same_invoke = str(current.get("last_invoke_id") or "") == invoke_payload["invoke_id"]
            still_running = str(current.get("dispatch_status") or "") == "running" and str(current.get("dispatch_role") or "") == role
            if same_invoke and still_running:
                update_task_fields(
                    self.app.conn,
                    task_id,
                    dispatch_status="submit_failed",
                    dispatch_role=role,
                    dispatch_started_at=None,
                    dispatch_attempts=attempts,
                    last_invoke_id=invoke_payload["invoke_id"],
                    last_event_summary=f"dispatch failed {role}: {invoke_payload['invoke_id']}",
                    dispatch_error_kind=submission_error_kind,
                    dispatch_error_status_code=submission_status_code,
                    dispatch_error_retryable=int(submission_retryable),
                    dispatch_error_message=submission_error,
                )
                self.app.conn.execute(
                    "UPDATE tasks SET last_event_at = datetime('now') WHERE task_id = ?",
                    (task_id,),
                )
                append_event(
                    self.app.conn,
                    task_id=task_id,
                    event_type="task.dispatch_failed",
                    actor="dispatcher",
                    action=role,
                    summary=f"dispatch failed {role}: {submission_error}",
                    idempotency_key=f"dispatch-failed:{invoke_payload['invoke_id']}",
                    trace_id=trace_id,
                )
                return {
                    "dispatched": False,
                    "reason": "submit_failed",
                    "task_id": task_id,
                    "invoke_payload": invoke_payload,
                    "runtime_submission": runtime_submission,
                    "submission_error": submission_error,
                    "submission_error_kind": submission_error_kind,
                    "submission_status_code": submission_status_code,
                    "submission_retryable": submission_retryable,
                    "submission_error_details": submission_error_details,
                }

        logger.info(
            "Runtime submission failure ignored after task progressed task=%s trace=%s invoke=%s",
            task_id,
            trace_id,
            invoke_payload["invoke_id"],
        )
        return {
            "dispatched": True,
            "task_id": task_id,
            "invoke_payload": invoke_payload,
            "runtime_submission": runtime_submission,
            "submission_error": submission_error,
            "submission_error_kind": submission_error_kind,
            "submission_status_code": submission_status_code,
            "submission_retryable": submission_retryable,
            "submission_error_details": submission_error_details,
            "submission_state": "late_failure_ignored",
        }

    def _now_expr_value(self) -> None:
        return None