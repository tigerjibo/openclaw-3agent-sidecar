from __future__ import annotations

from typing import Any

from ..adapters.agent_invoke import AgentInvokeAdapter
from ..adapters.openclaw_runtime import OpenClawRuntimeBridge
from ..api import TaskKernelApiApp
from ..events import append_event
from ..models import get_task_by_id, update_task_fields

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
        runtime_submission = self.runtime_bridge.submit_invoke(invoke_payload) if self.runtime_bridge is not None else None
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
        append_event(
            self.app.conn,
            task_id=task_id,
            event_type="task.dispatched",
            actor="dispatcher",
            action=role,
            summary=f"dispatch {role}: {invoke_payload['invoke_id']}",
            idempotency_key=f"dispatch:{invoke_payload['invoke_id']}",
        )
        self.app.conn.commit()
        return {
            "dispatched": True,
            "task_id": task_id,
            "invoke_payload": invoke_payload,
            "runtime_submission": runtime_submission,
        }

    def _now_expr_value(self) -> None:
        return None