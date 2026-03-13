from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.request import urlopen

from sidecar.adapters.ingress import IngressAdapter
from sidecar.models import update_task_fields
from sidecar.service_runner import ServiceRunner
from sidecar.time_utils import utc_now


def _create_task(runner: ServiceRunner, request_id: str) -> str:
    ingress = IngressAdapter(runner._app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-service-runner",
            "entrypoint": "institutional_task",
            "title": "service runner health task",
            "message": "用于 service runner health 测试。",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_service_runner_health_payload_includes_agent_health_snapshot() -> None:
    runner = ServiceRunner(config={"host": "127.0.0.1", "port": 0, "default_runtime_mode": "legacy_single", "maintenance_interval_sec": 0})

    try:
        runner.start()
        payload = runner.health_payload()
        agent_health = payload["agent_health"]
        maintenance = payload["maintenance"]
        assert isinstance(agent_health, dict)
        assert isinstance(maintenance, dict)

        assert payload["status"] == "ok"
        assert agent_health["status"] == "ok"
        assert agent_health["running_dispatch_count"] == 0
        assert maintenance["last_cycle"] is None
    finally:
        runner.stop()


def test_service_runner_health_payload_degrades_for_stale_dispatch() -> None:
    runner = ServiceRunner(config={"host": "127.0.0.1", "port": 0, "default_runtime_mode": "legacy_single", "maintenance_interval_sec": 0})
    conn = runner._app.conn
    assert conn is not None

    try:
        runner.start()
        _create_task(runner, request_id="req-service-runner-stale-maintenance-summary")
        runner.run_maintenance_cycle(now=utc_now())
        task_id = _create_task(runner, request_id="req-service-runner-stale")
        update_task_fields(
            conn,
            task_id,
            state="executing",
            current_role="executor",
            dispatch_status="running",
            dispatch_role="executor",
            dispatch_started_at=(utc_now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
        )

        payload = runner.health_payload(now=utc_now())
        agent_health = payload["agent_health"]
        maintenance = payload["maintenance"]
        assert isinstance(agent_health, dict)
        assert isinstance(maintenance, dict)

        assert payload["status"] == "degraded"
        assert agent_health["status"] == "degraded"
        assert task_id in agent_health["stale_dispatch_task_ids"]
        assert maintenance["last_cycle"] is not None
    finally:
        runner.stop()


def test_healthz_endpoint_returns_agent_health_snapshot() -> None:
    runner = ServiceRunner(config={"host": "127.0.0.1", "port": 0, "default_runtime_mode": "legacy_single", "maintenance_interval_sec": 0})

    try:
        runner.start()
        _create_task(runner, request_id="req-service-runner-healthz-maintenance")
        runner.run_maintenance_cycle(now=utc_now())
        assert runner.http_service.base_url is not None

        with urlopen(f"{runner.http_service.base_url}/healthz") as response:
            body = json.loads(response.read().decode("utf-8"))

        assert body["status"] == "ok"
        assert body["agent_health"]["status"] == "ok"
        assert "roles" in body["agent_health"]
        assert body["maintenance"]["last_cycle"] is not None
    finally:
        runner.stop()


def test_service_runner_health_payload_degrades_after_repeated_hook_registration_failures() -> None:
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
            "hook_registration_retry_sec": 1,
            "hook_registration_failure_alert_after": 2,
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.integration_payload(now=utc_now())
        retry_time = datetime.fromisoformat(str(first["gateway"]["hook_registration"]["next_retry_at"]))
        runner.run_maintenance_cycle(now=retry_time)
        payload = runner.health_payload(now=retry_time)
    finally:
        runner.stop()

    assert gateway.calls == 2
    assert payload["status"] == "degraded"
    assert payload["integration"]["gateway"]["hook_registration"]["status"] == "register_failed"
    assert payload["integration"]["gateway"]["hook_registration"]["attempt_count"] == 2


def test_service_runner_readiness_blocks_after_repeated_hook_registration_failures() -> None:
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
            "hook_registration_retry_sec": 1,
            "hook_registration_failure_alert_after": 2,
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.integration_payload(now=utc_now())
        retry_time = datetime.fromisoformat(str(first["gateway"]["hook_registration"]["next_retry_at"]))
        runner.run_maintenance_cycle(now=retry_time)
        payload = runner.readiness_payload()
    finally:
        runner.stop()

    assert gateway.calls == 2
    assert payload == {
        "status": "blocked",
        "reason": "integration=gateway_hook_registration",
    }


def test_readyz_endpoint_blocks_after_repeated_hook_registration_failures() -> None:
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
            "hook_registration_retry_sec": 1,
            "hook_registration_failure_alert_after": 2,
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.integration_payload(now=utc_now())
        retry_time = datetime.fromisoformat(str(first["gateway"]["hook_registration"]["next_retry_at"]))
        runner.run_maintenance_cycle(now=retry_time)
        assert runner.http_service.base_url is not None
        with urlopen(f"{runner.http_service.base_url}/readyz") as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        runner.stop()

    assert body == {
        "status": "blocked",
        "reason": "integration=gateway_hook_registration",
    }
