from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import contracts
from ..time_utils import ensure_utc, parse_utc_datetime, utc_now

_TERMINAL_STATES = {contracts.STATE_DONE, contracts.STATE_CANCELLED}
_ROLES = ("coordinator", "executor", "reviewer")


class AgentHealthMonitor:
    """Role-level health monitor based on current dispatch activity."""

    def __init__(self, app, *, stale_after_sec: int = 300) -> None:
        self.app = app
        self.stale_after_sec = int(stale_after_sec)

    def snapshot(self, *, now: datetime | None = None) -> dict[str, Any]:
        current = ensure_utc(now) if now is not None else utc_now()
        rows = self.app.conn.execute(
            """
            SELECT task_id, dispatch_role, dispatch_started_at
            FROM tasks
            WHERE dispatch_status = 'running'
              AND state NOT IN ('done', 'cancelled')
            ORDER BY created_at ASC, task_id ASC
            """
        ).fetchall()

        roles: dict[str, dict[str, Any]] = {
            role: {
                "status": "idle",
                "running_tasks": 0,
                "stale_task_ids": [],
            }
            for role in _ROLES
        }

        stale_task_ids: list[str] = []

        for row in rows:
            task_id = str(row["task_id"])
            role = str(row["dispatch_role"] or "").strip()
            if role not in roles:
                continue

            role_item = roles[role]
            role_item["running_tasks"] += 1
            role_item["status"] = "running"

            started_at = self._parse_datetime(row["dispatch_started_at"])
            if started_at is None:
                continue
            if (current - started_at).total_seconds() > self.stale_after_sec:
                role_item["status"] = "degraded"
                role_item["stale_task_ids"].append(task_id)
                stale_task_ids.append(task_id)

        status = contracts.HEALTH_DEGRADED if stale_task_ids else contracts.HEALTH_OK

        return {
            "status": status,
            "running_dispatch_count": len(rows),
            "stale_dispatch_task_ids": stale_task_ids,
            "roles": roles,
        }

    def _parse_datetime(self, value: Any) -> datetime | None:
        return parse_utc_datetime(value)
