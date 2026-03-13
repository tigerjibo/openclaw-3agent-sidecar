from __future__ import annotations

import json
import re
from typing import Any

from .. import contracts
from ..api import TaskKernelApiApp
from ..events import append_event
from ..models import Task, create_task, get_task_by_id


class IngressAdapter:
    def __init__(self, app: TaskKernelApiApp) -> None:
        self.app = app

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = self._require_str(payload, "request_id")
        entrypoint = self._require_str(payload, "entrypoint")
        if entrypoint != "institutional_task":
            raise ValueError(f"unsupported entrypoint: {entrypoint}")

        existing = self.app.conn.execute(
            "SELECT task_id FROM task_events WHERE idempotency_key = ? LIMIT 1",
            (request_id,),
        ).fetchone()
        if existing is not None:
            task = get_task_by_id(self.app.conn, str(existing["task_id"]))
            return {"created": False, "task_id": str(existing["task_id"]), "task": task}

        source = self._require_str(payload, "source")
        title = self._require_str(payload, "title")
        message = self._require_str(payload, "message")
        task_id = self._build_task_id(request_id)
        metadata = {
            "request_id": request_id,
            "source_message_id": payload.get("source_message_id"),
            "source_chat_id": payload.get("source_chat_id"),
            "metadata": payload.get("metadata") or {},
        }

        create_task(
            self.app.conn,
            Task(
                task_id=task_id,
                title=title,
                task_type=str(payload.get("task_type_hint") or "general"),
                source=source,
                created_by=(str(payload.get("source_user_id")) if payload.get("source_user_id") is not None else None),
                priority=str(payload.get("priority_hint") or "normal"),
                risk_level=str(payload.get("risk_level_hint") or "normal"),
                raw_request=message,
                metadata_json=json.dumps(metadata, ensure_ascii=False),
            ),
        )
        self.app.conn.execute(
            "UPDATE tasks SET last_event_at = datetime('now'), last_event_summary = ? WHERE task_id = ?",
            (f"ingress accepted: {title}", task_id),
        )
        append_event(
            self.app.conn,
            task_id=task_id,
            event_type=contracts.EVENT_TASK_CREATED,
            actor=source,
            action="ingress",
            summary=f"ingress accepted: {title}",
            idempotency_key=request_id,
        )
        self.app.conn.commit()
        return {"created": True, "task_id": task_id, "task": get_task_by_id(self.app.conn, task_id)}

    def _require_str(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        text = str(value).strip() if value is not None else ""
        if not text:
            raise ValueError(f"{key} is required")
        return text

    def _build_task_id(self, request_id: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", request_id).strip("-").lower()
        return f"task-{slug}"