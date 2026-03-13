from __future__ import annotations

import logging
import signal
import sys
import threading
from datetime import datetime
from typing import Any

from .api import TaskKernelApiApp
from .config import load_config
from .contracts import HEALTH_DEGRADED, HEALTH_FAILED, HEALTH_OK, READINESS_BLOCKED, READINESS_READY, READINESS_WARMING
from .http_service import LocalTaskKernelHttpService
from .metrics import compute_anomaly_summary
from .runtime.agent_health import AgentHealthMonitor
from .runtime.dispatcher import TaskDispatcher
from .runtime.recovery import TaskRecovery
from .runtime.scheduler import TaskScheduler
from .runtime_mode import RuntimeModeController
from .storage import connect, init_db

logger = logging.getLogger(__name__)


class ServiceRunner:
    """Managed local service entrypoint with lifecycle and graceful shutdown."""

    def __init__(self, *, config: dict | None = None) -> None:
        self._config = load_config()
        if config is not None:
            self._config.update(config)
        self.lifecycle_state = "starting"
        self._signal_handlers_installed = False

        conn = connect(self._config["db_path"])
        init_db(conn)
        controller = RuntimeModeController(production_model="default", mode=self._config["default_runtime_mode"])
        self._app = TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)
        self._dispatcher = TaskDispatcher(self._app)
        self._scheduler = TaskScheduler(self._app, dispatcher=self._dispatcher)
        self._recovery = TaskRecovery(
            self._app,
            executing_timeout_sec=int(self._config["executing_timeout_sec"]),
            reviewing_timeout_sec=int(self._config["reviewing_timeout_sec"]),
            blocked_alert_after_sec=int(self._config["blocked_alert_after_sec"]),
        )
        self._agent_health = AgentHealthMonitor(self._app)
        self._maintenance_stop = threading.Event()
        self._maintenance_thread: threading.Thread | None = None
        self._maintenance_lock = threading.Lock()
        self._last_maintenance_summary: dict[str, Any] | None = None
        self._http = LocalTaskKernelHttpService(app=self._app, host=self._config["host"], port=self._config["port"])
        self._http.service_runner = self  # type: ignore[attr-defined]

    @property
    def http_service(self) -> LocalTaskKernelHttpService:
        return self._http

    def start(self) -> None:
        if not self._signal_handlers_installed and threading.current_thread() is threading.main_thread():
            self.install_signal_handlers()
            self._signal_handlers_installed = True
        self._http.start()
        self.lifecycle_state = "ready"
        self._start_maintenance_loop()
        logger.info("Service started: %s mode=%s", self._http.base_url, self._config["default_runtime_mode"])

    def stop(self) -> None:
        self.lifecycle_state = "stopping"
        self._stop_maintenance_loop()
        self._http.stop()
        if self._app.conn is not None:
            self._app.conn.close()
        logger.info("Service stopped.")

    def run_maintenance_cycle(self, *, now: datetime | None = None) -> dict[str, Any]:
        cycle_time = now or datetime.utcnow()
        anomalies_before = self._anomalies_payload(now=cycle_time)
        recovery_summary = self._recovery.run_once(now=cycle_time)
        dispatched = self._scheduler.dispatch_ready_tasks(limit=10)
        anomalies_after = self._anomalies_payload(now=cycle_time)
        categories_before = self._ordered_categories(anomalies_before.get("by_category") or {})
        categories_after = self._ordered_categories(anomalies_after.get("by_category") or {})
        summary = {
            "cycle_started_at": cycle_time.isoformat(),
            "recovery": recovery_summary,
            "dispatched_count": len(dispatched),
            "dispatched_task_ids": [str(item["task_id"]) for item in dispatched],
            "anomaly_categories_before": categories_before,
            "anomaly_categories_after": categories_after,
            "resolved_categories": [category for category in categories_before if category not in categories_after],
        }
        with self._maintenance_lock:
            self._last_maintenance_summary = dict(summary)
        return summary

    def maintenance_payload(self) -> dict[str, Any]:
        with self._maintenance_lock:
            last_cycle = dict(self._last_maintenance_summary) if self._last_maintenance_summary is not None else None
        return {
            "status": HEALTH_OK if self.lifecycle_state == "ready" else HEALTH_FAILED,
            "interval_sec": self._config["maintenance_interval_sec"],
            "maintenance_enabled": float(self._config["maintenance_interval_sec"]) > 0,
            "last_cycle": last_cycle,
        }

    def ops_summary_payload(self, *, now: datetime | None = None) -> dict[str, Any]:
        health = self.health_payload(now=now)
        readiness = self.readiness_payload()
        maintenance = self.maintenance_payload()
        anomalies = self._anomalies_payload(now=now)
        operator_guidance = self._operator_guidance(health=health, readiness=readiness, anomalies=anomalies)
        intervention_summary = self._intervention_summary(health=health, anomalies=anomalies, maintenance=maintenance)
        return {
            "status": str(health["status"]),
            "lifecycle_state": self.lifecycle_state,
            "health": health,
            "readiness": readiness,
            "maintenance": maintenance,
            "anomalies": anomalies,
            "operator_guidance": operator_guidance,
            "intervention_summary": intervention_summary,
        }

    def health_payload(self, *, now: datetime | None = None) -> dict[str, object]:
        agent_health = self._agent_health.snapshot(now=now)
        maintenance = self.maintenance_payload()
        if self.lifecycle_state != "ready":
            return {"status": HEALTH_FAILED, "agent_health": agent_health, "maintenance": maintenance}
        if agent_health["status"] == HEALTH_DEGRADED:
            return {"status": HEALTH_DEGRADED, "agent_health": agent_health, "maintenance": maintenance}
        return {"status": HEALTH_OK, "agent_health": agent_health, "maintenance": maintenance}

    def readiness_payload(self) -> dict[str, str]:
        if self.lifecycle_state == "ready":
            return {"status": READINESS_READY}
        if self.lifecycle_state == "starting":
            return {"status": READINESS_WARMING, "reason": "service is starting"}
        return {"status": READINESS_BLOCKED, "reason": f"lifecycle={self.lifecycle_state}"}

    def install_signal_handlers(self) -> None:
        def _shutdown(signum: int, frame: object) -> None:
            logger.info("Received signal %s, shutting down...", signum)
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, _shutdown)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, _shutdown)

    def _start_maintenance_loop(self) -> None:
        interval = float(self._config["maintenance_interval_sec"])
        if interval <= 0:
            return
        if self._maintenance_thread is not None and self._maintenance_thread.is_alive():
            return
        self._maintenance_stop.clear()
        self._maintenance_thread = threading.Thread(
            target=self._maintenance_loop,
            name="service-runner-maintenance",
            daemon=True,
        )
        self._maintenance_thread.start()

    def _stop_maintenance_loop(self) -> None:
        self._maintenance_stop.set()
        if self._maintenance_thread is not None:
            self._maintenance_thread.join(timeout=2.0)
            self._maintenance_thread = None

    def _maintenance_loop(self) -> None:
        interval = float(self._config["maintenance_interval_sec"])
        while not self._maintenance_stop.is_set():
            try:
                summary = self.run_maintenance_cycle(now=datetime.utcnow())
                logger.debug("Maintenance cycle complete: %s", summary)
            except Exception:
                logger.exception("Maintenance cycle failed")
            if self._maintenance_stop.wait(timeout=interval):
                break

    def _anomalies_payload(self, *, now: datetime | None = None) -> dict[str, Any]:
        conn = self._app.conn
        if conn is None:
            return {"total_count": 0, "by_category": {}, "items": []}
        items = compute_anomaly_summary(
            conn,
            executing_timeout_sec=int(self._config["executing_timeout_sec"]),
            reviewing_timeout_sec=int(self._config["reviewing_timeout_sec"]),
            now=now,
        )
        by_category = {str(item["category"]): len(item.get("task_ids") or []) for item in items}
        return {
            "total_count": len(items),
            "by_category": by_category,
            "items": items,
        }

    def _operator_guidance(self, *, health: dict[str, object], readiness: dict[str, str], anomalies: dict[str, Any]) -> dict[str, str]:
        if str(health.get("status")) == HEALTH_DEGRADED or readiness.get("status") == READINESS_BLOCKED:
            return {
                "action": "manual_intervention",
                "rationale": "Service is degraded or blocked; operator intervention is recommended.",
            }
        if int(anomalies.get("total_count") or 0) > 0:
            categories = ", ".join(sorted(str(key) for key in (anomalies.get("by_category") or {}).keys()))
            return {
                "action": "investigate",
                "rationale": f"Anomalies detected in categories: {categories or 'unknown'}.",
            }
        return {
            "action": "observe",
            "rationale": "No active anomalies detected; continue observing normal operation.",
        }

    def _intervention_summary(self, *, health: dict[str, object], anomalies: dict[str, Any], maintenance: dict[str, Any]) -> dict[str, Any]:
        items = anomalies.get("items") or []
        by_category = anomalies.get("by_category") or {}
        priority_order = ["blocked", "execution_timeout", "review_timeout", "pending_human_confirm"]
        unresolved_categories = self._ordered_categories(by_category)

        priority_category: str | None = None
        for category in priority_order:
            if int(by_category.get(category) or 0) > 0:
                priority_category = category
                break

        attention_task_ids: list[str] = []
        if priority_category is not None:
            for item in items:
                if str(item.get("category")) == priority_category:
                    attention_task_ids = [str(task_id) for task_id in (item.get("task_ids") or [])]
                    break

        last_cycle = maintenance.get("last_cycle")
        resolved_categories: list[str] = []
        if isinstance(last_cycle, dict):
            resolved_categories = [str(category) for category in (last_cycle.get("resolved_categories") or [])]

        if int(anomalies.get("total_count") or 0) == 0:
            maintenance_effectiveness = "healthy"
        elif last_cycle is None:
            maintenance_effectiveness = "no_recent_maintenance"
        else:
            recovery = last_cycle.get("recovery") or {}
            had_actions = bool(last_cycle.get("dispatched_task_ids")) or any(bool(recovery.get(key)) for key in ("recover_dispatch", "retry_dispatch", "escalate_timeout", "escalate_blocked"))
            maintenance_effectiveness = "in_progress" if had_actions else "no_effect"

        if str(health.get("status")) == HEALTH_DEGRADED:
            attention_reason = "Service health is degraded; prioritize manual intervention before anomaly triage."
        elif priority_category is None:
            if resolved_categories:
                resolved_text = ", ".join(resolved_categories)
                attention_reason = f"Recent maintenance resolved previously detected {resolved_text} anomalies."
            else:
                attention_reason = "No active anomalies require intervention."
        elif maintenance_effectiveness == "no_recent_maintenance":
            attention_reason = f"Priority focus is {priority_category} because {priority_category} anomalies remain without a recent maintenance cycle."
        elif maintenance_effectiveness == "in_progress":
            attention_reason = f"Priority focus is {priority_category} because maintenance has started acting on it, but the anomaly remains active."
        elif maintenance_effectiveness == "no_effect":
            attention_reason = f"Priority focus is {priority_category} because recent maintenance did not reduce the active anomaly set."
        else:
            attention_reason = f"Priority focus is {priority_category} because it remains the highest-severity active anomaly category."

        return {
            "priority_category": priority_category,
            "attention_task_ids": attention_task_ids,
            "resolved_categories": resolved_categories,
            "unresolved_categories": unresolved_categories,
            "maintenance_effectiveness": maintenance_effectiveness,
            "attention_reason": attention_reason,
        }

    def _ordered_categories(self, by_category: dict[str, Any]) -> list[str]:
        priority_order = ["blocked", "execution_timeout", "review_timeout", "pending_human_confirm"]
        categories = [str(category) for category, count in by_category.items() if int(count or 0) > 0]
        ordered = [category for category in priority_order if category in categories]
        ordered.extend(sorted(category for category in categories if category not in priority_order))
        return ordered
