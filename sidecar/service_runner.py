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
        recovery_summary = self._recovery.run_once(now=cycle_time)
        dispatched = self._scheduler.dispatch_ready_tasks(limit=10)
        summary = {
            "cycle_started_at": cycle_time.isoformat(),
            "recovery": recovery_summary,
            "dispatched_count": len(dispatched),
            "dispatched_task_ids": [str(item["task_id"]) for item in dispatched],
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

    def health_payload(self, *, now: datetime | None = None) -> dict[str, object]:
        agent_health = self._agent_health.snapshot(now=now)
        if self.lifecycle_state != "ready":
            return {"status": HEALTH_FAILED, "agent_health": agent_health}
        if agent_health["status"] == HEALTH_DEGRADED:
            return {"status": HEALTH_DEGRADED, "agent_health": agent_health}
        return {"status": HEALTH_OK, "agent_health": agent_health}

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
