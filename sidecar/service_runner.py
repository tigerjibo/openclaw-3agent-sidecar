from __future__ import annotations

import logging
import signal
import sys
import threading
from datetime import datetime

from .api import TaskKernelApiApp
from .config import load_config
from .contracts import HEALTH_DEGRADED, HEALTH_FAILED, HEALTH_OK, READINESS_BLOCKED, READINESS_READY, READINESS_WARMING
from .http_service import LocalTaskKernelHttpService
from .runtime.agent_health import AgentHealthMonitor
from .runtime_mode import RuntimeModeController
from .storage import connect, init_db

logger = logging.getLogger(__name__)


class ServiceRunner:
    """Managed local service entrypoint with lifecycle and graceful shutdown."""

    def __init__(self, *, config: dict | None = None) -> None:
        self._config = config or load_config()
        self.lifecycle_state = "starting"
        self._signal_handlers_installed = False

        conn = connect(":memory:")
        init_db(conn)
        controller = RuntimeModeController(production_model="default", mode=self._config["default_runtime_mode"])
        self._app = TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)
        self._agent_health = AgentHealthMonitor(self._app)
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
        logger.info("Service started: %s mode=%s", self._http.base_url, self._config["default_runtime_mode"])

    def stop(self) -> None:
        self.lifecycle_state = "stopping"
        self._http.stop()
        if self._app.conn is not None:
            self._app.conn.close()
        logger.info("Service stopped.")

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
