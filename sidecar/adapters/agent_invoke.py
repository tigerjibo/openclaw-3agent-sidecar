from __future__ import annotations

import json
from typing import Any

from ..api import TaskKernelApiApp
from ..events import list_recent_events
from ..models import get_task_by_id
from ..runtime_mode import ROLE_NAMES

_ROLE_GOALS: dict[str, str] = {
    "coordinator": "归纳任务目标并形成 brief",
    "executor": "执行任务并提交证据与结果摘要",
    "reviewer": "审查结果并决定 approve 或 reject",
}


class AgentInvokeAdapter:
    def __init__(self, app: TaskKernelApiApp) -> None:
        self.app = app

    def build_invoke(self, task_id: str, *, role: str) -> dict[str, Any]:
        if role not in ROLE_NAMES:
            raise ValueError(f"unsupported role: {role}")
        task = get_task_by_id(self.app.conn, task_id)
        if task is None:
            raise ValueError(f"task not found: {task_id}")

        next_attempt = int(task.get("dispatch_attempts") or 0) + 1
        invoke_id = f"inv:{task_id}:{role}:v{task['version']}:a{next_attempt}"
        return {
            "invoke_id": invoke_id,
            "task_id": task_id,
            "role": role,
            "agent_id": role,
            "session_key": f"task:{task_id}:{role}",
            "goal": _ROLE_GOALS[role],
            "input": {
                "title": task.get("title"),
                "message": task.get("raw_request") or "",
                "task_context": self._task_context(task),
                "recent_events": list(reversed(list_recent_events(self.app.conn, task_id, limit=10))),
            },
            "constraints": {
                "timeout_seconds": 120,
                "deliver": False,
                "structured_output_required": True,
            },
        }

    def _task_context(self, task: dict[str, Any]) -> dict[str, Any]:
        context = dict(task)
        for key in ("acceptance_criteria", "risk_notes", "proposed_steps", "evidence", "open_issues", "followup_notes", "reasons", "required_rework"):
            context[key] = self._maybe_parse_json(context.get(key))
        return context

    def _maybe_parse_json(self, value: object) -> object:
        if value in (None, ""):
            return []
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value