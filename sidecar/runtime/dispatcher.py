from __future__ import annotations

import logging
from typing import Any

from ..adapters.agent_invoke import AgentInvokeAdapter
from ..adapters.openclaw_runtime import OpenClawRequestError, OpenClawRuntimeBridge
from ..api import TaskKernelApiApp
from ..events import append_event
from ..models import get_task_by_id, get_task_trace_id, mark_task_blocked, update_task_fields
from ..time_utils import utc_isoformat, utc_now

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {"done", "cancelled"}


class TaskDispatcher:
    def __init__(self, app: TaskKernelApiApp, *, runtime_bridge: OpenClawRuntimeBridge | None = None) -> None:
        self.app = app
        self.invoke_adapter = AgentInvokeAdapter(app)
        self.runtime_bridge = runtime_bridge
        self._last_runtime_submission_summary: dict[str, Any] | None = None

    def recent_runtime_submission_summary(self) -> dict[str, Any] | None:
        if self._last_runtime_submission_summary is None:
            return None
        return dict(self._last_runtime_submission_summary)

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
        submission_recovery_action = None
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
                submission_recovery_action = self._submission_recovery_action(kind=submission_error_kind, retryable=submission_retryable)
            except Exception as exc:
                logger.warning("Runtime submission failed for task=%s trace=%s msg=%s", task_id, trace_id, exc)
                submission_error = str(exc)
                submission_error_kind = "unexpected_error"
                submission_retryable = False
                submission_recovery_action = self._submission_recovery_action(kind=submission_error_kind, retryable=submission_retryable)
        if submission_error is None:
            if self.runtime_bridge is not None:
                self._record_runtime_submission(
                    task_id=task_id,
                    trace_id=trace_id,
                    status="accepted",
                    runtime_submission=runtime_submission,
                )
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
                    dispatch_status="idle" if submission_recovery_action == "block" else "submit_failed",
                    dispatch_role=None if submission_recovery_action == "block" else role,
                    dispatch_started_at=None,
                    dispatch_attempts=attempts,
                    last_invoke_id=invoke_payload["invoke_id"],
                    last_event_summary=(
                        f"dispatch blocked {role}: {invoke_payload['invoke_id']}"
                        if submission_recovery_action == "block"
                        else f"dispatch failed {role}: {invoke_payload['invoke_id']}"
                    ),
                    dispatch_error_kind=submission_error_kind,
                    dispatch_error_status_code=submission_status_code,
                    dispatch_error_retryable=int(submission_retryable),
                    dispatch_error_message=submission_error,
                )
                if submission_recovery_action == "block":
                    mark_task_blocked(
                        self.app.conn,
                        task_id,
                        reason=f"runtime configuration requires manual repair: {submission_error}",
                        waiting_on="runtime_configuration",
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
                    action=f"{role}:{submission_recovery_action or 'hold'}",
                    summary=(
                        f"dispatch blocked {role}: {submission_error}"
                        if submission_recovery_action == "block"
                        else f"dispatch failed {role}: {submission_error}"
                    ),
                    idempotency_key=f"dispatch-failed:{invoke_payload['invoke_id']}",
                    trace_id=trace_id,
                )
                self._record_runtime_submission(
                    task_id=task_id,
                    trace_id=trace_id,
                    status="blocked" if submission_recovery_action == "block" else "submit_failed",
                    runtime_submission=runtime_submission,
                    error_kind=submission_error_kind,
                    error_message=submission_error,
                    status_code=submission_status_code,
                    retryable=submission_retryable,
                    recovery_action=submission_recovery_action,
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
                    "submission_recovery_action": submission_recovery_action,
                }

        logger.info(
            "Runtime submission failure ignored after task progressed task=%s trace=%s invoke=%s",
            task_id,
            trace_id,
            invoke_payload["invoke_id"],
        )
        self._record_runtime_submission(
            task_id=task_id,
            trace_id=trace_id,
            status="late_failure_ignored",
            runtime_submission=runtime_submission,
            error_kind=submission_error_kind,
            error_message=submission_error,
            status_code=submission_status_code,
            retryable=submission_retryable,
            recovery_action="ignored",
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
            "submission_recovery_action": "ignored",
            "submission_state": "late_failure_ignored",
        }

    def _record_runtime_submission(
        self,
        *,
        task_id: str,
        trace_id: str,
        status: str,
        runtime_submission: dict[str, Any] | None,
        error_kind: str | None = None,
        error_message: str | None = None,
        status_code: int | None = None,
        retryable: bool = False,
        recovery_action: str | None = None,
    ) -> None:
        submission = dict(runtime_submission or {})
        response = dict(submission.get("response") or {})
        summary = {
            "last_submit_at": utc_isoformat(utc_now()),
            "last_submit_status": status,
            "last_submission_id": submission.get("submission_id"),
            "last_task_id": task_id,
            "last_trace_id": trace_id,
            "last_status_code": status_code if status_code is not None else submission.get("status_code"),
            "last_retryable": bool(retryable),
            "last_result_status": response.get("result_status"),
            "last_recovery_action": recovery_action,
            "last_error_kind": error_kind if error_kind is not None else response.get("result_error_kind"),
            "last_error_message": error_message if error_message is not None else response.get("result_error_message"),
        }
        self._last_runtime_submission_summary = summary

    def _submission_recovery_action(self, *, kind: str | None, retryable: bool) -> str:
        normalized_kind = str(kind or "").strip()
        if normalized_kind == "configuration_error":
            return "block"
        if retryable:
            return "retry"
        return "hold"

    def _now_expr_value(self) -> None:
        return None