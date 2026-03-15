from __future__ import annotations

import logging
import signal
import sys
import threading
from datetime import datetime, timedelta
from urllib.parse import urlparse
from typing import Any

from .api import TaskKernelApiApp
from .adapters.openclaw_runtime import CliOpenClawRuntimeBridge, HttpOpenClawRuntimeBridge, OpenClawGatewayClient, OpenClawRuntimeBridge
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
from .time_utils import ensure_utc, parse_utc_datetime, utc_isoformat, utc_now

logger = logging.getLogger(__name__)


class ServiceRunner:
    """Managed local service entrypoint with lifecycle and graceful shutdown.

    Persistence boundary
    --------------------
    Only *task* and *task_event* data live in SQLite and survive restarts.
    The following in-memory state is intentionally ephemeral and rebuilt
    automatically after a restart:
    - ``_maintenance_history`` / ``_last_maintenance_summary`` — populated
      after the first maintenance cycle.
    - ``_integration_probe_cache`` / ``_integration_probe_history`` — rebuilt
      on the next probe interval.
    - ``_hook_registration_state`` — re-attempted during ``start()``.
    """

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
        self._gateway_client = self._build_gateway_client()
        self._dispatcher = TaskDispatcher(self._app, runtime_bridge=self._build_runtime_bridge())
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
        self._maintenance_history: list[dict[str, Any]] = []
        self._integration_probe_lock = threading.Lock()
        self._integration_probe_cache: dict[str, Any] | None = None
        self._integration_probe_cached_at: datetime | None = None
        self._integration_probe_history: list[dict[str, Any]] = []
        self._hook_registration_state = self._default_hook_registration_state(status="not_configured")
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
        self._ensure_gateway_hooks_registered(now=utc_now())
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
        cycle_time = ensure_utc(now) if now is not None else utc_now()
        anomalies_before = self._anomalies_payload(now=cycle_time)
        recovery_summary = self._recovery.run_once(now=cycle_time)
        dispatched = self._scheduler.dispatch_ready_tasks(limit=10)
        hook_registration_before = dict(self._hook_registration_state)
        hook_registration_attempted = False
        if self._should_retry_hook_registration(now=cycle_time):
            hook_registration_attempted = True
            self._ensure_gateway_hooks_registered(now=cycle_time)
        hook_registration_after = dict(self._hook_registration_state)
        self._refresh_integration_probe_cache(now=cycle_time)
        anomalies_after = self._anomalies_payload(now=cycle_time)
        categories_before = self._ordered_categories(anomalies_before.get("by_category") or {})
        categories_after = self._ordered_categories(anomalies_after.get("by_category") or {})
        task_ids_before = self._ordered_task_ids(anomalies_before.get("items") or [])
        task_ids_after = self._ordered_task_ids(anomalies_after.get("items") or [])
        summary = {
            "cycle_started_at": utc_isoformat(cycle_time),
            "recovery": recovery_summary,
            "dispatched_count": len(dispatched),
            "dispatched_task_ids": [str(item["task_id"]) for item in dispatched],
            "hook_registration": {
                "attempted": hook_registration_attempted,
                "status_before": str(hook_registration_before.get("status") or "not_configured"),
                "status_after": str(hook_registration_after.get("status") or "not_configured"),
                "attempt_count": int(hook_registration_after.get("attempt_count") or 0),
            },
            "anomaly_categories_before": categories_before,
            "anomaly_categories_after": categories_after,
            "resolved_categories": [category for category in categories_before if category not in categories_after],
            "anomaly_task_ids_before": task_ids_before,
            "anomaly_task_ids_after": task_ids_after,
            "resolved_task_ids": [task_id for task_id in task_ids_before if task_id not in task_ids_after],
        }
        with self._maintenance_lock:
            self._last_maintenance_summary = dict(summary)
            self._maintenance_history.append(dict(summary))
            self._maintenance_history = self._maintenance_history[-10:]
        return summary

    def maintenance_payload(self, *, now: datetime | None = None, integration: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._maintenance_lock:
            last_cycle = dict(self._last_maintenance_summary) if self._last_maintenance_summary is not None else None
            history = [dict(item) for item in self._maintenance_history]
        integration_payload = integration if integration is not None else self.integration_payload(now=now)
        return {
            "status": HEALTH_OK if self.lifecycle_state == "ready" else HEALTH_FAILED,
            "interval_sec": self._config["maintenance_interval_sec"],
            "maintenance_enabled": float(self._config["maintenance_interval_sec"]) > 0,
            "last_cycle": last_cycle,
            "trend": self._maintenance_trend(history),
            "integration": integration_payload,
        }

    def ops_summary_payload(self, *, now: datetime | None = None) -> dict[str, Any]:
        integration = self.integration_payload(now=now)
        health = self.health_payload(now=now, integration=integration)
        readiness = self.readiness_payload()
        maintenance = self.maintenance_payload(now=now, integration=integration)
        anomalies = self._anomalies_payload(now=now)
        operator_guidance = self._operator_guidance(health=health, readiness=readiness, anomalies=anomalies, integration=integration)
        intervention_summary = self._intervention_summary(health=health, anomalies=anomalies, maintenance=maintenance)
        return {
            "status": str(health["status"]),
            "lifecycle_state": self.lifecycle_state,
            "health": health,
            "readiness": readiness,
            "maintenance": maintenance,
            "integration": integration,
            "anomalies": anomalies,
            "operator_guidance": operator_guidance,
            "intervention_summary": intervention_summary,
        }

    def health_payload(self, *, now: datetime | None = None, integration: dict[str, Any] | None = None) -> dict[str, object]:
        agent_health = self._agent_health.snapshot(now=now)
        integration_payload = integration if integration is not None else self.integration_payload(now=now)
        maintenance = self.maintenance_payload(now=now, integration=integration_payload)
        if self.lifecycle_state != "ready":
            return {"status": HEALTH_FAILED, "agent_health": agent_health, "maintenance": maintenance, "integration": integration_payload}
        if agent_health["status"] == HEALTH_DEGRADED or self._integration_health_degraded(integration_payload):
            return {"status": HEALTH_DEGRADED, "agent_health": agent_health, "maintenance": maintenance, "integration": integration_payload}
        return {"status": HEALTH_OK, "agent_health": agent_health, "maintenance": maintenance, "integration": integration_payload}

    def integration_payload(self, *, now: datetime | None = None) -> dict[str, Any]:
        gateway_base_url_configured = bool(str(self._config.get("gateway_base_url") or "").strip())
        hooks_token_configured = bool(str(self._config.get("hooks_token") or "").strip())
        public_base_url = str(self._config.get("public_base_url") or "").strip()
        runtime_invoke_url_configured = bool(str(self._config.get("runtime_invoke_url") or "").strip())
        result_callback_url = self._hook_callback_urls(public_base_url)[1] if public_base_url else None
        hook_registration = dict(self._hook_registration_state)
        gateway = {
            "gateway_base_url_configured": gateway_base_url_configured,
            "hooks_token_configured": hooks_token_configured,
            "client_available": self._gateway_client is not None,
            "hooks_enabled": gateway_base_url_configured and hooks_token_configured,
            "hook_registration_ready": str(hook_registration.get("status") or "") == "registered",
            "hook_delivery_status": self._hook_delivery_status(hook_registration),
            "hook_registration": hook_registration,
        }
        runtime_callback_missing_requirements: list[str] = []
        if runtime_invoke_url_configured and not public_base_url:
            runtime_callback_missing_requirements.append("public_base_url")
        if runtime_invoke_url_configured and not hooks_token_configured:
            runtime_callback_missing_requirements.append("hooks_token")
        runtime_invoke = {
            "invoke_url_configured": runtime_invoke_url_configured,
            "bridge_available": runtime_invoke_url_configured,
            "bridge": self._runtime_bridge_metadata(),
            "recent_submission": self._dispatcher.recent_runtime_submission_summary(),
            "result_callback_ready": runtime_invoke_url_configured and not runtime_callback_missing_requirements,
            "result_callback_url": result_callback_url if runtime_invoke_url_configured and result_callback_url else None,
            "missing_requirements": runtime_callback_missing_requirements,
        }

        if gateway["hooks_enabled"] and runtime_invoke["result_callback_ready"]:
            status = "fully_configured"
        elif gateway["hooks_enabled"] and not runtime_invoke_url_configured:
            status = "gateway_hooks_ready"
        elif runtime_invoke["result_callback_ready"]:
            status = "runtime_invoke_ready"
        elif gateway["hooks_enabled"]:
            status = "partially_configured"
        elif runtime_invoke_url_configured or gateway_base_url_configured or hooks_token_configured or bool(public_base_url):
            status = "partially_configured"
        else:
            status = "local_only"

        probe = self._integration_probe_payload(
            gateway_configured=gateway["client_available"],
            runtime_invoke_configured=runtime_invoke["bridge_available"],
            now=now,
        )

        return {
            "status": status,
            "gateway": gateway,
            "runtime_invoke": runtime_invoke,
            "probe": probe,
        }

    def _ensure_gateway_hooks_registered(self, *, now: datetime) -> None:
        now = ensure_utc(now)
        gateway_base_url_configured = bool(str(self._config.get("gateway_base_url") or "").strip())
        hooks_token_configured = bool(str(self._config.get("hooks_token") or "").strip())
        if self._gateway_client is None or not gateway_base_url_configured or not hooks_token_configured:
            self._hook_registration_state = self._default_hook_registration_state(status="not_configured")
            return

        public_base_url = str(self._config.get("public_base_url") or "").strip()
        if not public_base_url:
            self._hook_registration_state = self._default_hook_registration_state(
                status="missing_public_base_url",
                public_base_url=None,
                message="OPENCLAW_PUBLIC_BASE_URL is required for automatic gateway hook registration.",
            )
            return

        attempt_count = int((self._hook_registration_state or {}).get("attempt_count") or 0) + 1
        attempt_time = utc_isoformat(now)
        retry_sec = float(self._config.get("hook_registration_retry_sec") or 0)
        ingress_url, result_url = self._hook_callback_urls(public_base_url)
        try:
            response = self._gateway_client.register_hooks({
                "ingress_url": ingress_url,
                "result_url": result_url,
            })
        except Exception as exc:
            logger.exception("Automatic gateway hook registration failed")
            self._hook_registration_state = self._default_hook_registration_state(
                status="register_failed",
                last_attempt_at=attempt_time,
                next_retry_at=utc_isoformat(now + timedelta(seconds=retry_sec)) if retry_sec > 0 else attempt_time,
                attempt_count=attempt_count,
                public_base_url=public_base_url,
                ingress_url=ingress_url,
                result_url=result_url,
                message=str(exc),
            )
            return

        accepted = bool(response.get("accepted") or response.get("ok"))
        self._hook_registration_state = self._default_hook_registration_state(
            status="registered" if accepted else "register_rejected",
            registered_at=utc_isoformat(now) if accepted else None,
            last_attempt_at=attempt_time,
            next_retry_at=None if accepted else utc_isoformat(now + timedelta(seconds=retry_sec)) if retry_sec > 0 else attempt_time,
            attempt_count=attempt_count,
            public_base_url=public_base_url,
            ingress_url=ingress_url,
            result_url=result_url,
            accepted=accepted,
            status_code=response.get("status_code"),
            message=None if accepted else "Gateway hook registration was not accepted.",
        )

    def _default_hook_registration_state(
        self,
        *,
        status: str,
        registered_at: str | None = None,
        last_attempt_at: str | None = None,
        next_retry_at: str | None = None,
        attempt_count: int = 0,
        public_base_url: str | None = None,
        ingress_url: str | None = None,
        result_url: str | None = None,
        accepted: bool = False,
        status_code: int | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "registered_at": registered_at,
            "last_attempt_at": last_attempt_at,
            "next_retry_at": next_retry_at,
            "attempt_count": attempt_count,
            "public_base_url": public_base_url,
            "ingress_url": ingress_url,
            "result_url": result_url,
            "accepted": accepted,
            "status_code": status_code,
            "message": message,
        }

    def _hook_callback_urls(self, public_base_url: str) -> tuple[str, str]:
        base = str(public_base_url).strip().rstrip("/")
        return (
            f"{base}/hooks/openclaw/ingress",
            f"{base}/hooks/openclaw/result",
        )

    def _hook_delivery_status(self, hook_registration: dict[str, Any]) -> str:
        status = str(hook_registration.get("status") or "")
        if status == "registered":
            return "registered"
        if status == "missing_public_base_url":
            return "pending_public_base_url"
        if status in {"register_failed", "register_rejected"}:
            return "retry_wait" if hook_registration.get("next_retry_at") else "registration_failed"
        if status == "not_configured":
            return "not_configured"
        return "unknown"

    def _should_retry_hook_registration(self, *, now: datetime) -> bool:
        now = ensure_utc(now)
        status = str((self._hook_registration_state or {}).get("status") or "")
        if status not in {"register_failed", "register_rejected"}:
            return False
        next_retry_at = str((self._hook_registration_state or {}).get("next_retry_at") or "").strip()
        if not next_retry_at:
            return True
        retry_at = parse_utc_datetime(next_retry_at)
        if retry_at is None:
            return True
        return now >= retry_at

    def _integration_probe_payload(self, *, gateway_configured: bool, runtime_invoke_configured: bool, now: datetime | None = None) -> dict[str, Any]:
        if not gateway_configured and not runtime_invoke_configured:
            return {
                "status": "not_configured",
                "probed_at": None,
                "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
                "gateway": {"status": "not_configured", "ok": None, "status_code": None, "kind": None, "message": None},
                "runtime_invoke": {"status": "not_configured", "ok": None, "status_code": None, "kind": None, "message": None},
            }

        with self._integration_probe_lock:
            if self._integration_probe_cache is not None and not self._integration_probe_cache_expired(now=now):
                return dict(self._integration_probe_cache)

        return self._refresh_integration_probe_cache(now=now)

    def _refresh_integration_probe_cache(self, *, now: datetime | None = None) -> dict[str, Any]:
        probe_time = ensure_utc(now) if now is not None else utc_now()
        gateway_probe = self._probe_component(
            configured=self._gateway_client is not None,
            component=self._gateway_client,
        )
        runtime_probe = self._probe_component(
            configured=self._dispatcher.runtime_bridge is not None,
            component=self._dispatcher.runtime_bridge,
        )

        statuses = {str(item["status"]) for item in (gateway_probe, runtime_probe)}
        configured_probes = [item for item in (gateway_probe, runtime_probe) if item["status"] not in ("not_configured",)]
        if not configured_probes:
            status = "not_configured"
        elif all(item["status"] == "not_probed" for item in configured_probes):
            status = "not_probed"
        elif all(bool(item.get("ok")) for item in configured_probes):
            status = "reachable"
        elif any(bool(item.get("ok")) for item in configured_probes):
            status = "degraded"
        elif "not_probed" in statuses:
            status = "not_probed"
        else:
            status = "unreachable"

        history_item = {
            "probed_at": utc_isoformat(probe_time),
            "status": status,
            "gateway": dict(gateway_probe),
            "runtime_invoke": dict(runtime_probe),
        }
        with self._integration_probe_lock:
            self._integration_probe_history.append(history_item)
            self._integration_probe_history = self._integration_probe_history[-20:]
            history = list(self._integration_probe_history)

        overall_failure_stats = self._probe_failure_stats(history=history, component=None)
        gateway_probe = self._with_component_failure_stats(component_name="gateway", probe=gateway_probe, history=history)
        runtime_probe = self._with_component_failure_stats(component_name="runtime_invoke", probe=runtime_probe, history=history)

        payload = {
            "status": status,
            "probed_at": utc_isoformat(probe_time),
            "failure_stats": overall_failure_stats,
            "gateway": gateway_probe,
            "runtime_invoke": runtime_probe,
        }
        with self._integration_probe_lock:
            self._integration_probe_cache = dict(payload)
            self._integration_probe_cached_at = probe_time
        return dict(payload)

    def _integration_probe_cache_expired(self, *, now: datetime | None = None) -> bool:
        cached_at = self._integration_probe_cached_at
        if cached_at is None:
            return True
        ttl_sec = float(self._config.get("integration_probe_ttl_sec") or 0)
        if ttl_sec <= 0:
            return True
        check_time = ensure_utc(now) if now is not None else utc_now()
        return check_time - cached_at > timedelta(seconds=ttl_sec)

    def _probe_component(self, *, configured: bool, component: Any) -> dict[str, Any]:
        if not configured:
            return {
                "status": "not_configured",
                "ok": None,
                "status_code": None,
                "kind": None,
                "message": None,
            }

        probe_connectivity = getattr(component, "probe_connectivity", None)
        if callable(probe_connectivity):
            try:
                result = probe_connectivity()
            except Exception:
                logger.exception("Integration connectivity probe failed")
                return {
                    "status": "unreachable",
                    "ok": False,
                    "status_code": None,
                    "kind": "probe_exception",
                    "message": "Integration probe raised an exception.",
                }
            payload = {
                "status": str(result.get("status") or ("reachable" if result.get("ok") else "unreachable")),
                "ok": result.get("ok"),
                "status_code": result.get("status_code"),
                "kind": result.get("kind"),
                "message": result.get("message"),
            }
            return payload

        return {
            "status": "not_probed",
            "ok": None,
            "status_code": None,
            "kind": None,
            "message": None,
        }

    def readiness_payload(self) -> dict[str, str]:
        integration_block_reason = self._integration_readiness_block_reason()
        if integration_block_reason is not None:
            return {"status": READINESS_BLOCKED, "reason": integration_block_reason}
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
            if self._maintenance_stop.wait(timeout=interval):
                break
            try:
                summary = self.run_maintenance_cycle(now=utc_now())
                logger.debug("Maintenance cycle complete: %s", summary)
            except Exception:
                logger.exception("Maintenance cycle failed")

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

    def _operator_guidance(self, *, health: dict[str, object], readiness: dict[str, str], anomalies: dict[str, Any], integration: dict[str, Any]) -> dict[str, Any]:
        if str(health.get("status")) == HEALTH_DEGRADED or readiness.get("status") == READINESS_BLOCKED:
            return {
                "action": "manual_intervention",
                "rationale": "Service is degraded or blocked; operator intervention is recommended.",
            }
        integration_guidance = self._integration_operator_guidance(integration)
        if integration_guidance is not None:
            return integration_guidance
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

    def _integration_operator_guidance(self, integration: dict[str, Any]) -> dict[str, Any] | None:
        gateway = integration.get("gateway") or {}
        hook_registration = gateway.get("hook_registration") or {}
        registration_status = str(hook_registration.get("status") or "")
        if registration_status in {"register_failed", "register_rejected"}:
            details = str(hook_registration.get("message") or "gateway hook registration did not complete successfully")
            return {
                "action": "repair_hook_registration",
                "rationale": f"Gateway hook registration needs repair: {details}.",
            }

        probe = integration.get("probe") or {}
        if registration_status == "missing_public_base_url":
            gateway_probe = probe.get("gateway") or {}
            if not gateway_probe.get("kind"):
                return {
                    "action": "configure_public_base_url",
                    "rationale": "Gateway hooks are enabled but OPENCLAW_PUBLIC_BASE_URL is missing; configure an externally reachable base URL before automatic hook registration can succeed.",
                }

        for component_name in ("gateway", "runtime_invoke"):
            component = probe.get(component_name) or {}
            kind = str(component.get("kind") or "")
            if not kind:
                continue
            label = "gateway" if component_name == "gateway" else "runtime invoke"
            if kind == "network_error":
                return {
                    "action": "check_network",
                    "rationale": f"{label} probe reported network_error; check network, DNS, and firewall connectivity first.",
                }
            if kind == "configuration_error":
                return {
                    "action": "check_runtime_configuration",
                    "rationale": f"{label} probe reported configuration_error; inspect CLI binary path, agent id, and sidecar runtime wiring.",
                }
            if kind == "http_4xx":
                return {
                    "action": "check_integration_config",
                    "rationale": f"{label} probe reported http_4xx; check token, method, and route configuration.",
                }
            if kind == "http_5xx":
                return {
                    "action": "check_upstream_health",
                    "rationale": f"{label} probe reported http_5xx; 优先检查上游服务健康与错误日志。",
                }
            if kind == "runtime_error":
                return {
                    "action": "inspect_runtime_bridge",
                    "rationale": f"{label} probe reported runtime_error; inspect OpenClaw CLI availability, permissions, and upstream runtime stderr output.",
                }
            if kind in {"probe_error", "probe_exception"}:
                return {
                    "action": "investigate_probe",
                    "rationale": f"{label} probe failed internally; inspect sidecar probe execution and upstream endpoint behavior.",
                }
        runtime_invoke = integration.get("runtime_invoke") or {}
        if runtime_invoke.get("invoke_url_configured") and not runtime_invoke.get("result_callback_ready"):
            missing = ", ".join(str(item) for item in (runtime_invoke.get("missing_requirements") or [])) or "public_base_url, hooks_token"
            return {
                "action": "configure_runtime_callbacks",
                "rationale": f"Runtime invoke is configured but result callback wiring is incomplete; configure {missing} so OpenClaw can post results back to the sidecar.",
            }
        return None

    def _with_component_failure_stats(self, *, component_name: str, probe: dict[str, Any], history: list[dict[str, Any]]) -> dict[str, Any]:
        payload = dict(probe)
        payload["failure_stats"] = self._probe_failure_stats(history=history, component=component_name)
        return payload

    def _probe_failure_stats(self, *, history: list[dict[str, Any]], component: str | None) -> dict[str, int]:
        def _is_failure(item: dict[str, Any]) -> bool:
            if component is None:
                return str(item.get("status") or "") in {"degraded", "unreachable"}
            probe = item.get(component) or {}
            return probe.get("ok") is False

        recent_failure_count = sum(1 for item in history if _is_failure(item))
        consecutive_failure_count = 0
        for item in reversed(history):
            if _is_failure(item):
                consecutive_failure_count += 1
            else:
                break
        return {
            "recent_failure_count": recent_failure_count,
            "consecutive_failure_count": consecutive_failure_count,
        }

    def _intervention_summary(self, *, health: dict[str, object], anomalies: dict[str, Any], maintenance: dict[str, Any]) -> dict[str, Any]:
        items = anomalies.get("items") or []
        by_category = anomalies.get("by_category") or {}
        priority_order = ["blocked", "execution_timeout", "review_timeout", "pending_human_confirm"]
        unresolved_categories = self._ordered_categories(by_category)
        integration_attention = self._integration_attention_summary(maintenance)

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
        attention_tasks = [{"task_id": task_id, "category": priority_category} for task_id in attention_task_ids] if priority_category is not None else []

        last_cycle = maintenance.get("last_cycle")
        resolved_categories: list[str] = []
        resolved_task_ids: list[str] = []
        if isinstance(last_cycle, dict):
            resolved_categories = [str(category) for category in (last_cycle.get("resolved_categories") or [])]
            resolved_task_ids = [str(task_id) for task_id in (last_cycle.get("resolved_task_ids") or [])]

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
            elif integration_attention is not None:
                attention_reason = "No active task anomalies require intervention, but OpenClaw integration still needs operator attention."
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
            "attention_tasks": attention_tasks,
            "integration_attention": integration_attention,
            "resolved_categories": resolved_categories,
            "unresolved_categories": unresolved_categories,
            "resolved_task_ids": resolved_task_ids,
            "maintenance_effectiveness": maintenance_effectiveness,
            "attention_reason": attention_reason,
        }

    def _integration_attention_summary(self, maintenance: dict[str, Any]) -> dict[str, Any] | None:
        integration = maintenance.get("integration") or {}
        gateway = integration.get("gateway") or {}
        hook_registration = gateway.get("hook_registration") or {}
        status = str(hook_registration.get("status") or "")
        if status not in {"register_failed", "register_rejected", "missing_public_base_url"}:
            return None
        return {
            "component": "gateway_hook_registration",
            "status": status,
            "attempt_count": int(hook_registration.get("attempt_count") or 0),
            "next_retry_at": hook_registration.get("next_retry_at"),
            "message": hook_registration.get("message"),
        }

    def _integration_health_degraded(self, integration: dict[str, Any]) -> bool:
        gateway = integration.get("gateway") or {}
        hook_registration = gateway.get("hook_registration") or {}
        status = str(hook_registration.get("status") or "")
        if status not in {"register_failed", "register_rejected"}:
            return False
        attempt_count = int(hook_registration.get("attempt_count") or 0)
        alert_after = int(self._config.get("hook_registration_failure_alert_after") or 0)
        return alert_after > 0 and attempt_count >= alert_after

    def _integration_readiness_block_reason(self) -> str | None:
        hook_registration = self._hook_registration_state or {}
        status = str(hook_registration.get("status") or "")
        attempt_count = int(hook_registration.get("attempt_count") or 0)
        alert_after = int(self._config.get("hook_registration_failure_alert_after") or 0)
        if status in {"register_failed", "register_rejected"} and alert_after > 0 and attempt_count >= alert_after:
            return "integration=gateway_hook_registration"
        return None

    def _ordered_categories(self, by_category: dict[str, Any]) -> list[str]:
        priority_order = ["blocked", "execution_timeout", "review_timeout", "pending_human_confirm"]
        categories = [str(category) for category, count in by_category.items() if int(count or 0) > 0]
        ordered = [category for category in priority_order if category in categories]
        ordered.extend(sorted(category for category in categories if category not in priority_order))
        return ordered

    def _ordered_task_ids(self, items: list[dict[str, Any]]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for item in items:
            for task_id in item.get("task_ids") or []:
                text = str(task_id)
                if text in seen:
                    continue
                seen.add(text)
                ordered.append(text)
        return ordered

    def _maintenance_trend(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        latest_cycle_started_at = str(history[-1].get("cycle_started_at")) if history else None

        consecutive_no_effect_cycles = 0
        consecutive_in_progress_cycles = 0
        for item in reversed(history):
            effect = self._maintenance_effectiveness_for_cycle(item)
            if effect == "no_effect":
                consecutive_no_effect_cycles += 1
            else:
                break
        for item in reversed(history):
            effect = self._maintenance_effectiveness_for_cycle(item)
            if effect == "in_progress":
                consecutive_in_progress_cycles += 1
            else:
                break

        last_effective_cycle_started_at = None
        for item in reversed(history):
            effect = self._maintenance_effectiveness_for_cycle(item)
            if effect in ("resolved", "in_progress"):
                last_effective_cycle_started_at = str(item.get("cycle_started_at"))
                break

        latest = history[-1] if history else {}
        return {
            "recent_cycle_count": len(history),
            "latest_cycle_started_at": latest_cycle_started_at,
            "consecutive_no_effect_cycles": consecutive_no_effect_cycles,
            "consecutive_in_progress_cycles": consecutive_in_progress_cycles,
            "last_effective_cycle_started_at": last_effective_cycle_started_at,
            "recently_resolved_categories": [str(category) for category in (latest.get("resolved_categories") or [])],
            "recently_resolved_task_ids": [str(task_id) for task_id in (latest.get("resolved_task_ids") or [])],
        }

    def _maintenance_effectiveness_for_cycle(self, summary: dict[str, Any]) -> str:
        if summary.get("resolved_categories") or summary.get("resolved_task_ids"):
            return "resolved"
        recovery = summary.get("recovery") or {}
        had_actions = bool(summary.get("dispatched_task_ids")) or any(bool(recovery.get(key)) for key in ("recover_dispatch", "retry_dispatch", "escalate_timeout", "escalate_blocked"))
        return "in_progress" if had_actions else "no_effect"

    def _build_runtime_bridge(self) -> OpenClawRuntimeBridge | None:
        invoke_url = str(self._config.get("runtime_invoke_url") or "").strip()
        if not invoke_url:
            return None
        local_result_callback_url = ""
        host = str(self._config.get("host") or "").strip()
        port = int(self._config.get("port") or 0)
        if host and port > 0:
            local_result_callback_url = f"http://{host}:{port}/hooks/openclaw/result"
        public_base_url = str(self._config.get("public_base_url") or "").strip()
        hooks_token = str(self._config.get("hooks_token") or "").strip()
        result_callback_url = ""
        if public_base_url and hooks_token:
            _, result_callback_url = self._hook_callback_urls(public_base_url)
        parsed = urlparse(invoke_url)
        if parsed.scheme in {"openclaw-cli", "openclaw-agent"}:
            agent_id = (parsed.netloc or parsed.path or "").lstrip("/").strip() or "main"
            return CliOpenClawRuntimeBridge(
                agent_id=agent_id,
                result_callback_url=local_result_callback_url or result_callback_url,
                hooks_token=hooks_token,
            )
        return HttpOpenClawRuntimeBridge(
            invoke_url,
            result_callback_url=result_callback_url,
            hooks_token=hooks_token,
        )

    def _build_gateway_client(self) -> OpenClawGatewayClient | None:
        gateway_base_url = str(self._config.get("gateway_base_url") or "").strip()
        if not gateway_base_url:
            return None
        return OpenClawGatewayClient(gateway_base_url, hooks_token=str(self._config.get("hooks_token") or "").strip())

    def _runtime_bridge_metadata(self) -> dict[str, Any] | None:
        bridge = self._dispatcher.runtime_bridge
        if bridge is None:
            return None
        describe = getattr(bridge, "describe", None)
        if not callable(describe):
            return {"kind": bridge.__class__.__name__}
        try:
            metadata = describe()
        except Exception:
            logger.exception("Failed to describe runtime bridge")
            return {"kind": bridge.__class__.__name__, "describe_error": True}
        return dict(metadata or {"kind": bridge.__class__.__name__})
