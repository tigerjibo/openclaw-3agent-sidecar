from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from urllib.request import urlopen

from sidecar.adapters.ingress import IngressAdapter
from sidecar.config import load_config
from sidecar.models import get_task_by_id, update_task_fields
from sidecar.service_runner import ServiceRunner


def _create_task(runner: ServiceRunner, request_id: str) -> str:
    ingress = IngressAdapter(runner._app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-service-runner-runtime-loop",
            "entrypoint": "institutional_task",
            "title": "runtime loop task",
            "message": "用于 service runner runtime loop 测试。",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_load_config_reads_maintenance_interval_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_MAINTENANCE_INTERVAL_SEC", "7")

    config = load_config()

    assert config["maintenance_interval_sec"] == 7


def test_load_config_reads_integration_probe_ttl_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_INTEGRATION_PROBE_TTL_SEC", "42")

    config = load_config()

    assert config["integration_probe_ttl_sec"] == 42


def test_service_runner_run_maintenance_cycle_recovers_timeout_and_dispatches_ready_task() -> None:
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "executing_timeout_sec": 60,
            "reviewing_timeout_sec": 60,
            "blocked_alert_after_sec": 60,
        }
    )
    conn = runner._app.conn
    assert conn is not None

    try:
        runner.start()

        ready_task_id = _create_task(runner, request_id="req-service-runner-maint-ready")
        stale_task_id = _create_task(runner, request_id="req-service-runner-maint-stale")
        update_task_fields(
            conn,
            stale_task_id,
            state="executing",
            current_role="executor",
            dispatch_status="running",
            dispatch_role="executor",
            dispatch_started_at=(datetime.utcnow() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        )

        summary = runner.run_maintenance_cycle(now=datetime.utcnow())
        ready_task = get_task_by_id(conn, ready_task_id)
        stale_task = get_task_by_id(conn, stale_task_id)
    finally:
        runner.stop()

    assert stale_task_id in summary["recovery"]["escalate_timeout"]
    assert ready_task_id in summary["dispatched_task_ids"]
    assert ready_task is not None
    assert ready_task["dispatch_status"] == "running"
    assert ready_task["dispatch_role"] == "coordinator"
    assert stale_task is not None
    assert stale_task["dispatch_status"] == "running"
    assert stale_task["dispatch_role"] == "executor"


def test_service_runner_background_runtime_loop_dispatches_task() -> None:
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0.05,
        }
    )
    conn = runner._app.conn
    assert conn is not None

    try:
        runner.start()
        task_id = _create_task(runner, request_id="req-service-runner-background-loop")

        deadline = time.time() + 2.0
        task = get_task_by_id(conn, task_id)
        while time.time() < deadline and (task is None or task["dispatch_status"] != "running"):
            time.sleep(0.05)
            task = get_task_by_id(conn, task_id)
    finally:
        runner.stop()

    assert task is not None
    assert task["dispatch_status"] == "running"
    assert task["dispatch_role"] == "coordinator"


def test_service_runner_maintenance_cycle_recovers_persisted_inflight_task_after_restart(tmp_path) -> None:
    db_path = tmp_path / "state" / "runtime-loop.sqlite3"
    config = {
        "host": "127.0.0.1",
        "port": 0,
        "default_runtime_mode": "legacy_single",
        "db_path": str(db_path),
        "maintenance_interval_sec": 0,
        "executing_timeout_sec": 3600,
        "reviewing_timeout_sec": 3600,
        "blocked_alert_after_sec": 3600,
    }

    first_runner = ServiceRunner(config=config)
    try:
        first_runner.start()
        task_id = _create_task(first_runner, request_id="req-service-runner-restart-inflight")
        summary_before_stop = first_runner.run_maintenance_cycle(now=datetime.utcnow())
        assert task_id in summary_before_stop["dispatched_task_ids"]
    finally:
        first_runner.stop()

    second_runner = ServiceRunner(config=config)
    conn = second_runner._app.conn
    assert conn is not None
    try:
        second_runner.start()
        summary_after_restart = second_runner.run_maintenance_cycle(now=datetime.utcnow())
        task = get_task_by_id(conn, task_id)
    finally:
        second_runner.stop()

    assert task_id in summary_after_restart["recovery"]["recover_dispatch"]
    assert task_id in summary_after_restart["dispatched_task_ids"]
    assert task is not None
    assert task["dispatch_status"] == "running"
    assert task["dispatch_role"] == "coordinator"
    assert task["dispatch_attempts"] == 2


def test_service_runner_maintenance_cycle_escalates_blocked_task_without_dispatching_it() -> None:
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "blocked_alert_after_sec": 60,
        }
    )
    conn = runner._app.conn
    assert conn is not None

    try:
        runner.start()
        task_id = _create_task(runner, request_id="req-service-runner-blocked-no-dispatch")
        update_task_fields(
            conn,
            task_id,
            blocked=1,
            block_reason="waiting external dependency",
            block_since=(datetime.utcnow() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        )

        summary = runner.run_maintenance_cycle(now=datetime.utcnow())
        task = get_task_by_id(conn, task_id)
    finally:
        runner.stop()

    assert task_id in summary["recovery"]["escalate_blocked"]
    assert task_id not in summary["dispatched_task_ids"]
    assert task is not None
    assert task["blocked"] == 1
    assert task["dispatch_status"] == "idle"


def test_service_runner_maintenance_payload_reports_last_cycle_summary() -> None:
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
        }
    )

    try:
        runner.start()
        task_id = _create_task(runner, request_id="req-service-runner-maintenance-payload")

        before = runner.maintenance_payload()
        summary = runner.run_maintenance_cycle(now=datetime.utcnow())
        after = runner.maintenance_payload()
    finally:
        runner.stop()

    assert before["last_cycle"] is None
    assert after["interval_sec"] == 0
    assert after["last_cycle"] is not None
    assert "integration" in after
    assert "probe" in after["integration"]
    assert after["last_cycle"]["dispatched_count"] == summary["dispatched_count"]
    assert task_id in after["last_cycle"]["dispatched_task_ids"]


def test_runtime_maintenance_endpoint_returns_last_cycle_summary() -> None:
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
        }
    )

    try:
        runner.start()
        _create_task(runner, request_id="req-service-runner-maintenance-endpoint")
        runner.run_maintenance_cycle(now=datetime.utcnow())
        assert runner.http_service.base_url is not None

        with urlopen(f"{runner.http_service.base_url}/runtime/maintenance") as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        runner.stop()

    assert body["status"] == "ok"
    assert body["maintenance"]["last_cycle"] is not None
    assert "integration" in body["maintenance"]
    assert "probe" in body["maintenance"]["integration"]
    assert body["maintenance"]["last_cycle"]["dispatched_count"] >= 1


def test_maintenance_cycle_retries_failed_gateway_hook_registration() -> None:
    class FlakyGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("gateway offline")
            return {"accepted": True, "ok": True, "status_code": 202, "response": {"registered": True}}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    gateway = FlakyGatewayClient()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com/kernel",
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.integration_payload(now=datetime.utcnow())
        retry_time = datetime.fromisoformat(str(first["gateway"]["hook_registration"]["next_retry_at"]))
        runner.run_maintenance_cycle(now=retry_time)
        second = runner.integration_payload(now=retry_time)
    finally:
        runner.stop()

    assert gateway.calls == 2
    assert first["gateway"]["hook_registration"]["status"] == "register_failed"
    assert second["gateway"]["hook_registration"] == {
        "status": "registered",
        "registered_at": retry_time.isoformat(),
        "last_attempt_at": retry_time.isoformat(),
        "next_retry_at": None,
        "attempt_count": 2,
        "public_base_url": "https://sidecar.example.com/kernel",
        "ingress_url": "https://sidecar.example.com/kernel/hooks/openclaw/ingress",
        "result_url": "https://sidecar.example.com/kernel/hooks/openclaw/result",
        "accepted": True,
        "status_code": 202,
        "message": None,
    }


def test_maintenance_cycle_skips_hook_reregistration_after_success() -> None:
    class StableGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            return {"accepted": True, "ok": True, "status_code": 202, "response": {"registered": True}}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    gateway = StableGatewayClient()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com/kernel",
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        runner.run_maintenance_cycle(now=datetime(2026, 3, 13, 4, 15, 0))
        payload = runner.integration_payload(now=datetime(2026, 3, 13, 4, 15, 0))
    finally:
        runner.stop()

    assert gateway.calls == 1
    assert payload["gateway"]["hook_registration"]["status"] == "registered"
    assert payload["gateway"]["hook_registration"]["attempt_count"] == 1


def test_maintenance_cycle_respects_hook_registration_retry_interval_after_failure() -> None:
    class FailingGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            raise RuntimeError("gateway offline")

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": None, "kind": "network_error", "message": "Unable to reach OpenClaw gateway."}

    gateway = FailingGatewayClient()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com/kernel",
            "hook_registration_retry_sec": 600,
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.integration_payload(now=datetime.utcnow())
        retry_time = datetime.fromisoformat(str(first["gateway"]["hook_registration"]["next_retry_at"]))
        before_retry = retry_time - timedelta(seconds=1)
        runner.run_maintenance_cycle(now=before_retry)
        second = runner.integration_payload(now=before_retry)
    finally:
        runner.stop()

    assert gateway.calls == 1
    assert first["gateway"]["hook_registration"]["status"] == "register_failed"
    assert first["gateway"]["hook_registration"]["next_retry_at"] == first["gateway"]["hook_registration"]["next_retry_at"]
    assert second["gateway"]["hook_registration"] == first["gateway"]["hook_registration"]


def test_maintenance_cycle_retries_hook_registration_after_retry_interval_elapsed() -> None:
    class FlakyGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("gateway offline")
            return {"accepted": True, "ok": True, "status_code": 202, "response": {"registered": True}}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    gateway = FlakyGatewayClient()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com/kernel",
            "hook_registration_retry_sec": 60,
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.integration_payload(now=datetime.utcnow())
        retry_time = datetime.fromisoformat(str(first["gateway"]["hook_registration"]["next_retry_at"]))
        retry_after = retry_time + timedelta(seconds=1)
        runner.run_maintenance_cycle(now=retry_after)
        second = runner.integration_payload(now=retry_after)
    finally:
        runner.stop()

    assert gateway.calls == 2
    assert first["gateway"]["hook_registration"]["status"] == "register_failed"
    assert first["gateway"]["hook_registration"]["next_retry_at"] == first["gateway"]["hook_registration"]["next_retry_at"]
    assert second["gateway"]["hook_registration"]["status"] == "registered"
    assert second["gateway"]["hook_registration"]["attempt_count"] == 2
    assert second["gateway"]["hook_registration"]["next_retry_at"] is None


def test_maintenance_cycle_reports_hook_registration_retry_activity() -> None:
    class FlakyGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("gateway offline")
            return {"accepted": True, "ok": True, "status_code": 202, "response": {"registered": True}}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    gateway = FlakyGatewayClient()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com/kernel",
            "hook_registration_retry_sec": 60,
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.integration_payload(now=datetime.utcnow())
        retry_time = datetime.fromisoformat(str(first["gateway"]["hook_registration"]["next_retry_at"]))
        summary = runner.run_maintenance_cycle(now=retry_time)
    finally:
        runner.stop()

    assert summary["hook_registration"] == {
        "attempted": True,
        "status_before": "register_failed",
        "status_after": "registered",
        "attempt_count": 2,
    }


def test_maintenance_cycle_reports_skipped_hook_registration_retry_before_window() -> None:
    class FailingGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            self.calls += 1
            raise RuntimeError("gateway offline")

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": None, "kind": "network_error", "message": "Unable to reach OpenClaw gateway."}

    gateway = FailingGatewayClient()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com/kernel",
            "hook_registration_retry_sec": 600,
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.integration_payload(now=datetime.utcnow())
        retry_time = datetime.fromisoformat(str(first["gateway"]["hook_registration"]["next_retry_at"]))
        summary = runner.run_maintenance_cycle(now=retry_time - timedelta(seconds=1))
    finally:
        runner.stop()

    assert summary["hook_registration"] == {
        "attempted": False,
        "status_before": "register_failed",
        "status_after": "register_failed",
        "attempt_count": 1,
    }
