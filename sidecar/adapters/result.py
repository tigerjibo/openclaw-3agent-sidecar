from __future__ import annotations

from typing import Any

from .. import contracts
from ..api import TaskKernelApiApp
from ..events import append_event
from ..models import get_task_by_id, update_task_fields


class ResultAdapter:
    def __init__(self, app: TaskKernelApiApp) -> None:
        self.app = app

    def apply_result(self, payload: dict[str, Any], *, channel: str = "local") -> dict[str, Any]:
        conn = self._conn()
        invoke_id = self._require_str(payload, "invoke_id")
        task_id = self._require_str(payload, "task_id")
        role = self._require_str(payload, "role")
        status = self._require_str(payload, "status")
        output = payload.get("output") or {}

        task = get_task_by_id(conn, task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")

        existing = conn.execute(
            "SELECT 1 FROM task_events WHERE task_id = ? AND idempotency_key = ? LIMIT 1",
            (task_id, invoke_id),
        ).fetchone()
        if existing is not None:
            current = get_task_by_id(conn, task_id)
            if current is None:
                raise ValueError(f"task not found after replay: {task_id}")
            return current

        append_event(
            conn,
            task_id=task_id,
            event_type="task.result_received",
            actor=role,
            action=status,
            summary=f"{role} result received via {channel}: {status}",
            idempotency_key=invoke_id,
        )

        if status == "succeeded":
            result = self._apply_success(task_id, role=role, output=output)
        elif status == "blocked":
            reason = str((output or {}).get("blocked_reason") or payload.get("error") or "blocked")
            response = self.app.handle_request("POST", f"/tasks/{task_id}/block", body={"actor_role": role, "reason": reason, "idempotency_key": f"block:{invoke_id}"})
            result = response["body"]["data"]
        else:
            reason = str(payload.get("error") or f"{role} execution failed")
            response = self.app.handle_request("POST", f"/tasks/{task_id}/block", body={"actor_role": role, "reason": reason, "idempotency_key": f"fail:{invoke_id}"})
            result = response["body"]["data"]

        update_task_fields(
            conn,
            task_id,
            last_invoke_id=invoke_id,
            dispatch_status="idle",
            dispatch_role=None,
            dispatch_started_at=None,
        )
        conn.commit()
        current = get_task_by_id(conn, task_id)
        if current is None:
            raise ValueError(f"task not found after applying result: {task_id}")
        return current

    def _apply_success(self, task_id: str, *, role: str, output: dict[str, Any]) -> dict[str, Any]:
        if role == "coordinator":
            return self._apply_coordinator_success(task_id, output)
        if role == "executor":
            return self._apply_executor_success(task_id, output)
        if role == "reviewer":
            return self._apply_reviewer_success(task_id, output)
        raise ValueError(f"unsupported role: {role}")

    def _apply_coordinator_success(self, task_id: str, output: dict[str, Any]) -> dict[str, Any]:
        update_task_fields(
            self._conn(),
            task_id,
            goal=str(output.get("goal") or ""),
            acceptance_criteria=output.get("acceptance_criteria") or [],
            risk_notes=output.get("risk_notes") or [],
            proposed_steps=output.get("proposed_steps") or [],
        )
        task = self._must_get_task(task_id)
        expected_version = int(task["version"])
        if str(task["state"]) == contracts.STATE_INBOX:
            self._must_ok(
                self.app.handle_request("POST", f"/tasks/{task_id}/transition", body={"actor_role": "coordinator", "new_state": contracts.STATE_TRIAGING, "expected_version": expected_version})
            )
            task = self._must_get_task(task_id)
            expected_version = int(task["version"])
        if str(task["state"]) == contracts.STATE_TRIAGING:
            self._must_ok(
                self.app.handle_request("POST", f"/tasks/{task_id}/transition", body={"actor_role": "coordinator", "new_state": contracts.STATE_QUEUED, "expected_version": expected_version})
            )
        return self._must_get_task(task_id)

    def _apply_executor_success(self, task_id: str, output: dict[str, Any]) -> dict[str, Any]:
        task = self._must_get_task(task_id)
        expected_version = int(task["version"])
        if str(task["state"]) in (contracts.STATE_QUEUED, contracts.STATE_REWORK):
            self._must_ok(
                self.app.handle_request("POST", f"/tasks/{task_id}/transition", body={"actor_role": "executor", "new_state": contracts.STATE_EXECUTING, "expected_version": expected_version})
            )
        update_task_fields(
            self._conn(),
            task_id,
            result_summary=str(output.get("result_summary") or ""),
            evidence=output.get("evidence") or [],
            open_issues=output.get("open_issues") or [],
            followup_notes=output.get("followup_notes") or [],
        )
        task = self._must_get_task(task_id)
        if str(task["state"]) == contracts.STATE_EXECUTING:
            self._must_ok(
                self.app.handle_request("POST", f"/tasks/{task_id}/transition", body={"actor_role": "executor", "new_state": contracts.STATE_REVIEWING, "expected_version": int(task['version'])})
            )
        return self._must_get_task(task_id)

    def _apply_reviewer_success(self, task_id: str, output: dict[str, Any]) -> dict[str, Any]:
        decision = self._require_str(output, "review_decision")
        comment = str(output.get("review_comment") or "")
        task = self._must_get_task(task_id)
        response = self.app.handle_request(
            "POST",
            f"/tasks/{task_id}/review",
            body={
                "actor_role": "reviewer",
                "decision": decision,
                "comment": comment,
                "expected_version": int(task["version"]),
            },
        )
        updated = self._must_ok(response)
        update_task_fields(
            self._conn(),
            task_id,
            reasons=output.get("reasons") or [],
            required_rework=output.get("required_rework") or [],
            residual_risk=str(output.get("residual_risk") or ""),
        )
        return updated

    def _must_get_task(self, task_id: str) -> dict[str, Any]:
        task = get_task_by_id(self._conn(), task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")
        return task

    def _conn(self):
        conn = self.app.conn
        if conn is None:
            raise RuntimeError("TaskKernelApiApp connection is not initialized")
        return conn

    def _must_ok(self, response: dict[str, Any]) -> dict[str, Any]:
        if response.get("status") not in (200, 201):
            raise ValueError(str(response))
        return dict(response["body"]["data"])

    def _require_str(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError(f"{key} is required")
        return text