from __future__ import annotations

import logging
from typing import Any

from ..adapters.agent_invoke import AgentInvokeAdapter
from ..adapters.openclaw_runtime import OpenClawRuntimeBridge
from ..api import TaskKernelApiApp
from ..events import append_event
from ..models import get_task_by_id, update_task_fields

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
        runtime_submission = None
        submission_error = None
        if self.runtime_bridge is not None:
            try:
                runtime_submission = self.runtime_bridge.submit_invoke(invoke_payload)
            except Exception as exc:
                logger.warning("Runtime submission failed for %s: %s", task_id, exc)
                submission_error = str(exc)
        attempts = int(task.get("dispatch_attempts") or 0) + 1
        update_task_fields(
            self.app.conn,
            task_id,
            dispatch_status="running",
            dispatch_role=role,
            dispatch_started_at=self._now_expr_value(),
            dispatch_attempts=attempts,
            last_invoke_id=invoke_payload["invoke_id"],
            last_event_summary=f"dispatch {role}: {invoke_payload['invoke_id']}",
        )
        self.app.conn.execute(
            "UPDATE tasks SET dispatch_started_at = datetime('now'), last_event_at = datetime('now') WHERE task_id = ?",
            (task_id,),
        )
        event_summary = f"dispatch {role}: {invoke_payload['invoke_id']}"
        if submission_error:
            event_summary += f" (submission failed: {submission_error})"
        append_event(
            self.app.conn,
            task_id=task_id,
            event_type="task.dispatched",
            actor="dispatcher",
            action=role,
            summary=event_summary,
            idempotency_key=f"dispatch:{invoke_payload['invoke_id']}",
        )
        self.app.conn.commit()
        result: dict[str, Any] = {
            "dispatched": True,
            "task_id": task_id,
            "invoke_payload": invoke_payload,
            "runtime_submission": runtime_submission,
        }
        if submission_error:
            result["submission_error"] = submission_error
        return result

    def _now_expr_value(self) -> None:
        return None