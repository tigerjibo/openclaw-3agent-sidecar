from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any, Optional

from . import contracts
from .events import append_event
from .models import (
    Task,
    clear_task_blocked,
    create_task,
    get_task_by_id,
    list_tasks,
    mark_task_blocked,
)
from .runtime_mode import RuntimeModeController
from .state_machine import apply_rework_priority_flags, can_actor_transition
from .storage import connect, init_db


def get_runtime_mode_status(controller: RuntimeModeController) -> dict[str, object]:
    return controller.snapshot()


@dataclass
class TaskKernelApiApp:
    runtime_mode_controller: RuntimeModeController
    conn: sqlite3.Connection | None = None

    def __post_init__(self) -> None:
        if self.conn is None:
            self.conn = connect(":memory:")
            init_db(self.conn)

    def handle_request(self, method: str, path: str, *, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        if method == "GET" and path == "/runtime-mode":
            return self._ok_response(get_runtime_mode_status(self.runtime_mode_controller))

        if method == "POST" and path == "/runtime-mode":
            request_body = body or {}
            mode = request_body.get("mode")
            force = bool(request_body.get("force", False))
            if not mode:
                return self._error_response(status=400, code=contracts.ERR_VALIDATION, message="mode is required", details={"field": "mode"})
            try:
                snapshot = self.runtime_mode_controller.switch_mode(mode, force=force)
            except ValueError as exc:
                return self._error_response(status=400, code=contracts.ERR_VALIDATION, message=str(exc), details={"field": "mode", "value": mode})
            return self._ok_response(snapshot)

        if method == "POST" and path == "/tasks":
            return self._create_task(body or {})

        if method == "GET" and path == "/tasks":
            return self._ok_response(list_tasks(self.conn))

        if method == "GET" and path.startswith("/tasks/"):
            if path.endswith(("/transition", "/review", "/block", "/unblock", "/cancel", "/human-action")):
                return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"route not found: {method} {path}", details={"method": method, "path": path})
            task_id = path.rsplit("/", 1)[-1]
            task = get_task_by_id(self.conn, task_id)
            if task is None:
                return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"task not found: {task_id}", details={"task_id": task_id})
            return self._ok_response(task)

        if method == "POST" and path.endswith("/transition"):
            return self._transition_task(path.split("/")[2], body or {})
        if method == "POST" and path.endswith("/review"):
            return self._review_task(path.split("/")[2], body or {})
        if method == "POST" and path.endswith("/block"):
            return self._block_task(path.split("/")[2], body or {})
        if method == "POST" and path.endswith("/unblock"):
            return self._unblock_task(path.split("/")[2], body or {})
        if method == "POST" and path.endswith("/cancel"):
            return self._cancel_task(path.split("/")[2], body or {})
        if method == "POST" and path.endswith("/human-action"):
            return self._human_action(path.split("/")[2], body or {})

        return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"route not found: {method} {path}", details={"method": method, "path": path})

    def _create_task(self, request_body: dict[str, Any]) -> dict[str, Any]:
        required_fields = ("task_id", "title", "task_type")
        missing_fields = [field for field in required_fields if not request_body.get(field)]
        if missing_fields:
            return self._error_response(status=400, code=contracts.ERR_VALIDATION, message="missing required task fields", details={"missing_fields": missing_fields})

        task = Task(
            task_id=str(request_body["task_id"]),
            title=str(request_body["title"]),
            task_type=str(request_body["task_type"]),
            state=str(request_body.get("state", contracts.STATE_INBOX)),
            current_role=str(request_body.get("current_role", "coordinator")),
            priority=str(request_body.get("priority", "normal")),
            risk_level=str(request_body.get("risk_level", "normal")),
            requires_human_confirm=bool(request_body.get("requires_human_confirm", False)),
            source=request_body.get("source"),
            created_by=request_body.get("created_by"),
        )
        create_task(self.conn, task)
        self.conn.commit()
        return {"status": 201, "body": {"ok": True, "data": get_task_by_id(self.conn, task.task_id)}}

    def _transition_task(self, task_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        task = get_task_by_id(self.conn, task_id)
        if task is None:
            return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"task not found: {task_id}", details={"task_id": task_id})
        conflict = self._check_expected_version(task, request_body.get("expected_version"))
        if conflict is not None:
            return conflict
        actor_role = str(request_body.get("actor_role", ""))
        new_state = str(request_body.get("new_state", ""))
        if not can_actor_transition(actor_role, task["state"], new_state):
            return self._error_response(status=400, code=contracts.ERR_INVALID_STATE, message=f"invalid transition: {task['state']} -> {new_state}", details={"task_id": task_id, "old_state": task['state'], "new_state": new_state, "actor_role": actor_role})
        updated = self._update_task_state(task, new_state=new_state, actor_role=actor_role, event_type=contracts.EVENT_TASK_TRANSITIONED, action=contracts.ACTION_TRANSITION, summary=f"{task['state']} -> {new_state}")
        return self._ok_response(updated)

    def _review_task(self, task_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        task = get_task_by_id(self.conn, task_id)
        if task is None:
            return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"task not found: {task_id}", details={"task_id": task_id})
        conflict = self._check_expected_version(task, request_body.get("expected_version"))
        if conflict is not None:
            return conflict
        replay = self._idempotent_replay(task_id, request_body)
        if replay is not None:
            return replay
        decision = str(request_body.get("decision", ""))
        actor_role = str(request_body.get("actor_role", ""))
        comment = str(request_body.get("comment", ""))
        if decision == "approve":
            new_state = contracts.STATE_DONE
        elif decision == "reject":
            new_state = contracts.STATE_REWORK
        else:
            return self._error_response(status=400, code=contracts.ERR_VALIDATION, message="decision must be approve or reject", details={"field": "decision", "value": decision})
        if not can_actor_transition(actor_role, task["state"], new_state):
            return self._error_response(status=400, code=contracts.ERR_INVALID_STATE, message=f"invalid review transition: {task['state']} -> {new_state}", details={"task_id": task_id, "old_state": task['state'], "new_state": new_state, "actor_role": actor_role})
        updated = self._update_task_state(
            task,
            new_state=new_state,
            actor_role=actor_role,
            event_type=contracts.EVENT_TASK_REVIEWED,
            action=(contracts.ACTION_REVIEW_APPROVE if decision == "approve" else contracts.ACTION_REVIEW_REJECT),
            summary=f"review {decision}: {comment}".strip(),
            idempotency_key=self._get_idempotency_key(request_body),
            review_decision=decision,
            review_comment=comment,
            increment_review_round=True,
        )
        return self._ok_response(updated)

    def _block_task(self, task_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        task = get_task_by_id(self.conn, task_id)
        if task is None:
            return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"task not found: {task_id}", details={"task_id": task_id})
        replay = self._idempotent_replay(task_id, request_body)
        if replay is not None:
            return replay
        reason = str(request_body.get("reason", "")).strip()
        if not reason:
            return self._error_response(status=400, code=contracts.ERR_VALIDATION, message="reason is required", details={"field": "reason"})
        mark_task_blocked(self.conn, task_id, reason=reason, waiting_on=request_body.get("waiting_on"))
        self.conn.execute("UPDATE tasks SET version = version + 1, last_event_at = datetime('now'), last_event_summary = ? WHERE task_id = ?", (f"blocked: {reason}", task_id))
        append_event(self.conn, task_id=task_id, event_type=contracts.EVENT_TASK_BLOCKED, actor=str(request_body.get("actor_role", "")) or None, action=contracts.ACTION_BLOCK, summary=f"blocked: {reason}", idempotency_key=self._get_idempotency_key(request_body))
        self.conn.commit()
        return self._ok_response(get_task_by_id(self.conn, task_id))

    def _unblock_task(self, task_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        task = get_task_by_id(self.conn, task_id)
        if task is None:
            return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"task not found: {task_id}", details={"task_id": task_id})
        replay = self._idempotent_replay(task_id, request_body)
        if replay is not None:
            return replay
        clear_task_blocked(self.conn, task_id)
        self.conn.execute("UPDATE tasks SET version = version + 1, last_event_at = datetime('now'), last_event_summary = ? WHERE task_id = ?", ("unblocked", task_id))
        append_event(self.conn, task_id=task_id, event_type=contracts.EVENT_TASK_UNBLOCKED, actor=str(request_body.get("actor_role", "")) or None, action=contracts.ACTION_UNBLOCK, summary="unblocked", idempotency_key=self._get_idempotency_key(request_body))
        self.conn.commit()
        return self._ok_response(get_task_by_id(self.conn, task_id))

    def _cancel_task(self, task_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        task = get_task_by_id(self.conn, task_id)
        if task is None:
            return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"task not found: {task_id}", details={"task_id": task_id})
        conflict = self._check_expected_version(task, request_body.get("expected_version"))
        if conflict is not None:
            return conflict
        replay = self._idempotent_replay(task_id, request_body)
        if replay is not None:
            return replay
        actor_role = str(request_body.get("actor_role", ""))
        if not can_actor_transition(actor_role, task["state"], contracts.STATE_CANCELLED):
            return self._error_response(status=400, code=contracts.ERR_INVALID_STATE, message=f"invalid cancel transition: {task['state']} -> {contracts.STATE_CANCELLED}", details={"task_id": task_id, "old_state": task['state'], "new_state": contracts.STATE_CANCELLED, "actor_role": actor_role})
        updated = self._update_task_state(task, new_state=contracts.STATE_CANCELLED, actor_role=actor_role, event_type=contracts.EVENT_TASK_CANCELLED, action=contracts.ACTION_CANCEL, summary="task cancelled", idempotency_key=self._get_idempotency_key(request_body))
        return self._ok_response(updated)

    def _human_action(self, task_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
        task = get_task_by_id(self.conn, task_id)
        if task is None:
            return self._error_response(status=404, code=contracts.ERR_NOT_FOUND, message=f"task not found: {task_id}", details={"task_id": task_id})
        action = str(request_body.get("action", "")).strip()
        allowed_actions = {"confirm_done", "reject_to_rework", "block", "unblock", "cancel"}
        if action not in allowed_actions:
            return self._error_response(status=400, code=contracts.ERR_VALIDATION, message="unsupported human action", details={"action": action})
        if action == "confirm_done":
            if str(task["state"]) != contracts.STATE_DONE:
                return self._error_response(status=400, code=contracts.ERR_INVALID_STATE, message="confirm_done requires task state done", details={"task_id": task_id, "state": task['state']})
            self.conn.execute("UPDATE tasks SET version = version + 1, last_event_at = datetime('now'), last_event_summary = ? WHERE task_id = ?", ("human confirmed done", task_id))
            append_event(self.conn, task_id=task_id, event_type=contracts.EVENT_TASK_DONE_CONFIRMED, actor="human", action=contracts.ACTION_CONFIRM_DONE, summary="human confirmed done")
            self.conn.commit()
            return self._ok_response(get_task_by_id(self.conn, task_id))
        if action == "reject_to_rework":
            if str(task["state"]) != contracts.STATE_REVIEWING:
                return self._error_response(status=400, code=contracts.ERR_INVALID_STATE, message="reject_to_rework requires task state reviewing", details={"task_id": task_id, "state": task['state']})
            updated = self._update_task_state(task, new_state=contracts.STATE_REWORK, actor_role="human", event_type=contracts.EVENT_TASK_REVIEWED, action=contracts.ACTION_REVIEW_REJECT, summary=f"human rejected to rework: {str(request_body.get('comment', ''))}".strip(), review_decision="reject", review_comment=str(request_body.get("comment", "")), increment_review_round=True)
            return self._ok_response(updated)
        if action == "block":
            return self._block_task(task_id, {**request_body, "actor_role": "human"})
        if action == "unblock":
            return self._unblock_task(task_id, {**request_body, "actor_role": "human"})
        return self._cancel_task(task_id, {**request_body, "actor_role": str(task.get("current_role") or self._role_for_state(str(task['state'])) or "coordinator"), "expected_version": request_body.get("expected_version", task["version"])})

    def _update_task_state(self, task: dict[str, Any], *, new_state: str, actor_role: str, event_type: str, action: str, summary: str, idempotency_key: Optional[str] = None, review_decision: Optional[str] = None, review_comment: Optional[str] = None, increment_review_round: bool = False) -> dict[str, Any]:
        available, used = apply_rework_priority_flags(old_state=str(task["state"]), new_state=new_state, rework_priority_available=bool(task.get("rework_priority_available", 0)), rework_priority_used=bool(task.get("rework_priority_used", 0)))
        next_role = self._role_for_state(new_state)
        next_review_round = int(task.get("review_round", 0)) + (1 if increment_review_round else 0)
        next_version = int(task["version"]) + 1
        self.conn.execute(
            """
            UPDATE tasks
            SET state = ?,
                current_role = ?,
                version = ?,
                review_decision = COALESCE(?, review_decision),
                review_comment = COALESCE(?, review_comment),
                review_round = ?,
                rework_priority_available = ?,
                rework_priority_used = ?,
                updated_at = datetime('now'),
                last_event_at = datetime('now'),
                last_event_summary = ?
            WHERE task_id = ?
            """,
            (new_state, next_role, next_version, review_decision, review_comment, next_review_round, int(available), int(used), summary, task["task_id"]),
        )
        append_event(self.conn, task_id=str(task["task_id"]), event_type=event_type, actor=actor_role, action=action, summary=summary, idempotency_key=idempotency_key)
        self.conn.commit()
        return get_task_by_id(self.conn, str(task["task_id"]))

    def _idempotent_replay(self, task_id: str, request_body: dict[str, Any]) -> dict[str, Any] | None:
        idempotency_key = self._get_idempotency_key(request_body)
        if not idempotency_key:
            return None
        row = self.conn.execute("SELECT 1 FROM task_events WHERE task_id = ? AND idempotency_key = ? LIMIT 1", (task_id, idempotency_key)).fetchone()
        if row is None:
            return None
        return self._ok_response(get_task_by_id(self.conn, task_id))

    def _get_idempotency_key(self, request_body: dict[str, Any]) -> Optional[str]:
        value = request_body.get("idempotency_key")
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _check_expected_version(self, task: dict[str, Any], expected_version: Any) -> dict[str, Any] | None:
        if expected_version is None:
            return self._error_response(status=400, code=contracts.ERR_VALIDATION, message="expected_version is required", details={"field": "expected_version"})
        if int(expected_version) != int(task["version"]):
            return self._error_response(status=409, code=contracts.ERR_CONFLICT, message="stale task version", details={"task_id": task['task_id'], "expected_version": expected_version, "current_version": task['version']})
        return None

    def _role_for_state(self, state: str) -> Optional[str]:
        return {
            contracts.STATE_INBOX: "coordinator",
            contracts.STATE_TRIAGING: "coordinator",
            contracts.STATE_QUEUED: "executor",
            contracts.STATE_EXECUTING: "executor",
            contracts.STATE_REVIEWING: "reviewer",
            contracts.STATE_REWORK: "executor",
        }.get(state)

    def _ok_response(self, data: Any) -> dict[str, Any]:
        return {"status": 200, "body": {"ok": True, "data": data}}

    def _error_response(self, *, status: int, code: str, message: str, details: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return {"status": status, "body": {"ok": False, "error": True, "code": code, "message": message, "details": details or {}}}
