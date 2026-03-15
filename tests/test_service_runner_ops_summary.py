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
            "source_user_id": "user-service-runner-ops-summary",
            "entrypoint": "institutional_task",
            "title": "ops summary task",
            "message": "用于 ops summary 测试。",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_service_runner_ops_summary_payload_aggregates_health_readiness_and_maintenance() -> None:
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
        task_id = _create_task(runner, request_id="req-service-runner-ops-summary")
        runner.run_maintenance_cycle(now=utc_now())
        payload = runner.ops_summary_payload(now=utc_now())
    finally:
        runner.stop()

    assert payload["status"] == "ok"
    assert payload["lifecycle_state"] == "ready"
    assert payload["health"]["status"] == "ok"
    assert payload["readiness"]["status"] == "ready"
    assert payload["maintenance"]["last_cycle"] is not None
    assert payload["integration"]["status"] == "local_only"
    assert payload["integration"]["gateway"]["client_available"] is False
    assert payload["integration"]["runtime_invoke"]["bridge_available"] is False
    assert payload["integration"]["probe"] == {
        "status": "not_configured",
        "probed_at": None,
        "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        "gateway": {"status": "not_configured", "ok": None, "status_code": None, "kind": None, "message": None},
        "runtime_invoke": {"status": "not_configured", "ok": None, "status_code": None, "kind": None, "message": None},
    }
    assert payload["anomalies"]["total_count"] == 0
    assert payload["operator_guidance"]["action"] == "observe"
    assert payload["intervention_summary"]["priority_category"] is None
    assert payload["intervention_summary"]["attention_task_ids"] == []
    assert payload["intervention_summary"]["resolved_categories"] == []
    assert payload["intervention_summary"]["unresolved_categories"] == []
    assert payload["intervention_summary"]["attention_reason"] == "No active anomalies require intervention."
    assert task_id in payload["maintenance"]["last_cycle"]["dispatched_task_ids"]


def test_ops_summary_payload_surfaces_blocked_anomaly_and_investigate_guidance() -> None:
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
        task_id = _create_task(runner, request_id="req-service-runner-ops-summary-blocked")
        update_task_fields(
            conn,
            task_id,
            blocked=1,
            block_reason="waiting human input",
            block_since=(utc_now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        )

        payload = runner.ops_summary_payload(now=utc_now())
    finally:
        runner.stop()

    assert payload["anomalies"]["total_count"] == 1
    assert payload["anomalies"]["by_category"]["blocked"] == 1
    assert task_id in payload["anomalies"]["items"][0]["task_ids"]
    assert payload["operator_guidance"]["action"] == "investigate"
    assert payload["intervention_summary"]["priority_category"] == "blocked"
    assert payload["intervention_summary"]["attention_task_ids"] == [task_id]
    assert payload["intervention_summary"]["maintenance_effectiveness"] == "no_recent_maintenance"
    assert payload["intervention_summary"]["resolved_categories"] == []
    assert payload["intervention_summary"]["unresolved_categories"] == ["blocked"]
    assert payload["intervention_summary"]["resolved_task_ids"] == []
    assert payload["intervention_summary"]["attention_tasks"] == [{"task_id": task_id, "category": "blocked"}]
    assert payload["intervention_summary"]["attention_reason"] == "Priority focus is blocked because blocked anomalies remain without a recent maintenance cycle."


def test_ops_summary_payload_prefers_manual_intervention_when_health_is_degraded() -> None:
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
        }
    )
    conn = runner._app.conn
    assert conn is not None

    try:
        runner.start()
        task_id = _create_task(runner, request_id="req-service-runner-ops-summary-degraded")
        update_task_fields(
            conn,
            task_id,
            state="executing",
            current_role="executor",
            dispatch_status="running",
            dispatch_role="executor",
            dispatch_started_at="2026-03-13 00:00:00",
        )

        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 1, 0, 0))
    finally:
        runner.stop()

    assert payload["health"]["status"] == "degraded"
    assert payload["health"]["integration"]["status"] == "local_only"
    assert payload["operator_guidance"]["action"] == "manual_intervention"
    assert payload["intervention_summary"]["priority_category"] is None
    assert payload["intervention_summary"]["attention_reason"] == "Service health is degraded; prioritize manual intervention before anomaly triage."


def test_ops_summary_payload_reports_partial_runtime_integration_without_public_callback_base() -> None:
    class FakeGatewayClient:
        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    class FakeRuntimeBridge:
        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 204, "kind": None, "message": None}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 300,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._gateway_client = FakeGatewayClient()  # type: ignore[assignment]
    runner._dispatcher.runtime_bridge = FakeRuntimeBridge()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=utc_now())
    finally:
        runner.stop()

    assert payload["integration"]["status"] == "partially_configured"
    assert payload["integration"]["gateway"] == {
        "gateway_base_url_configured": True,
        "hooks_token_configured": True,
        "client_available": True,
        "hooks_enabled": True,
        "hook_registration_ready": False,
        "hook_delivery_status": "pending_public_base_url",
        "hook_registration": {
            "status": "missing_public_base_url",
            "registered_at": None,
            "last_attempt_at": None,
            "next_retry_at": None,
            "attempt_count": 0,
            "public_base_url": None,
            "ingress_url": None,
            "result_url": None,
            "accepted": False,
            "status_code": None,
            "message": "OPENCLAW_PUBLIC_BASE_URL is required for automatic gateway hook registration.",
        },
    }
    assert payload["integration"]["runtime_invoke"] == {
        "invoke_url_configured": True,
        "bridge_available": True,
        "bridge": {"kind": "FakeRuntimeBridge"},
        "result_callback_ready": False,
        "result_callback_url": None,
        "missing_requirements": ["public_base_url"],
    }
    assert payload["health"]["integration"]["status"] == "partially_configured"
    assert payload["operator_guidance"]["action"] == "configure_public_base_url"


def test_service_runner_start_registers_gateway_hooks_when_public_base_url_is_configured() -> None:
    class FakeGatewayClient:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            self.payloads.append(dict(payload))
            return {"accepted": True, "ok": True, "status_code": 202, "response": {"registered": True}}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    gateway = FakeGatewayClient()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com/kernel/",
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.integration_payload(now=datetime(2026, 3, 13, 3, 0, 0))
    finally:
        runner.stop()

    assert gateway.payloads == [
        {
            "ingress_url": "https://sidecar.example.com/kernel/hooks/openclaw/ingress",
            "result_url": "https://sidecar.example.com/kernel/hooks/openclaw/result",
        }
    ]
    assert payload["gateway"]["hook_registration"] == {
        "status": "registered",
        "registered_at": payload["gateway"]["hook_registration"]["registered_at"],
        "last_attempt_at": payload["gateway"]["hook_registration"]["last_attempt_at"],
        "next_retry_at": None,
        "attempt_count": 1,
        "public_base_url": "https://sidecar.example.com/kernel/",
        "ingress_url": "https://sidecar.example.com/kernel/hooks/openclaw/ingress",
        "result_url": "https://sidecar.example.com/kernel/hooks/openclaw/result",
        "accepted": True,
        "status_code": 202,
        "message": None,
    }
    assert payload["gateway"]["hook_registration_ready"] is True
    assert payload["gateway"]["hook_delivery_status"] == "registered"


def test_service_runner_reports_missing_public_base_url_for_hook_registration() -> None:
    class FakeGatewayClient:
        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
        }
    )
    runner._gateway_client = FakeGatewayClient()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.integration_payload(now=datetime(2026, 3, 13, 3, 5, 0))
    finally:
        runner.stop()

    assert payload["gateway"]["hook_registration"] == {
        "status": "missing_public_base_url",
        "registered_at": None,
        "last_attempt_at": None,
        "next_retry_at": None,
        "attempt_count": 0,
        "public_base_url": None,
        "ingress_url": None,
        "result_url": None,
        "accepted": False,
        "status_code": None,
        "message": "OPENCLAW_PUBLIC_BASE_URL is required for automatic gateway hook registration.",
    }
    assert payload["gateway"]["hook_registration_ready"] is False
    assert payload["gateway"]["hook_delivery_status"] == "pending_public_base_url"


def test_service_runner_surfaces_hook_registration_failure_in_integration_payload() -> None:
    class FailingGatewayClient:
        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("gateway offline")

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": None, "kind": "network_error", "message": "Unable to reach OpenClaw gateway."}

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
    runner._gateway_client = FailingGatewayClient()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.integration_payload(now=datetime(2026, 3, 13, 3, 10, 0))
    finally:
        runner.stop()

    assert payload["gateway"]["hook_registration"] == {
        "status": "register_failed",
        "registered_at": None,
        "last_attempt_at": payload["gateway"]["hook_registration"]["last_attempt_at"],
        "next_retry_at": payload["gateway"]["hook_registration"]["next_retry_at"],
        "attempt_count": 1,
        "public_base_url": "https://sidecar.example.com/kernel",
        "ingress_url": "https://sidecar.example.com/kernel/hooks/openclaw/ingress",
        "result_url": "https://sidecar.example.com/kernel/hooks/openclaw/result",
        "accepted": False,
        "status_code": None,
        "message": "gateway offline",
    }
    assert payload["gateway"]["hook_registration_ready"] is False
    assert payload["gateway"]["hook_delivery_status"] == "retry_wait"


def test_ops_summary_payload_reports_probe_results_for_gateway_and_runtime() -> None:
    class FakeGatewayClient:
        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    class FakeRuntimeBridge:
        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": 503, "kind": "http_5xx", "message": "503 from runtime invoke endpoint."}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 300,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._gateway_client = FakeGatewayClient()  # type: ignore[assignment]
    runner._dispatcher.runtime_bridge = FakeRuntimeBridge()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 0, 0))
    finally:
        runner.stop()

    assert payload["integration"]["probe"] == {
        "status": "degraded",
        "probed_at": "2026-03-13T02:00:00",
        "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        "gateway": {
            "status": "reachable",
            "ok": True,
            "status_code": 200,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        },
        "runtime_invoke": {
            "status": "unreachable",
            "ok": False,
            "status_code": 503,
            "kind": "http_5xx",
            "message": "503 from runtime invoke endpoint.",
            "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        },
    }


def test_ops_summary_payload_preserves_structured_probe_failure_reasons() -> None:
    class FakeGatewayClient:
        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": None, "kind": "network_error", "message": "Unable to reach OpenClaw gateway."}

    class FakeRuntimeBridge:
        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 405, "kind": "http_4xx", "message": "405 from runtime invoke endpoint."}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 300,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._gateway_client = FakeGatewayClient()  # type: ignore[assignment]
    runner._dispatcher.runtime_bridge = FakeRuntimeBridge()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 1, 0))
    finally:
        runner.stop()

    assert payload["integration"]["probe"] == {
        "status": "degraded",
        "probed_at": "2026-03-13T02:01:00",
        "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        "gateway": {
            "status": "unreachable",
            "ok": False,
            "status_code": None,
            "kind": "network_error",
            "message": "Unable to reach OpenClaw gateway.",
            "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        },
        "runtime_invoke": {
            "status": "reachable",
            "ok": True,
            "status_code": 405,
            "kind": "http_4xx",
            "message": "405 from runtime invoke endpoint.",
            "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        },
    }


def test_ops_summary_payload_tracks_recent_and_consecutive_probe_failures() -> None:
    class FakeGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def probe_connectivity(self) -> dict[str, object]:
            self.calls += 1
            if self.calls <= 2:
                return {"status": "unreachable", "ok": False, "status_code": None, "kind": "network_error", "message": "Unable to reach OpenClaw gateway."}
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    class FakeRuntimeBridge:
        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 204, "kind": None, "message": None}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 30,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._gateway_client = FakeGatewayClient()  # type: ignore[assignment]
    runner._dispatcher.runtime_bridge = FakeRuntimeBridge()  # type: ignore[assignment]

    try:
        runner.start()
        runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 30, 0))
        runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 30, 31))
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 31, 2))
    finally:
        runner.stop()

    assert payload["integration"]["probe"]["status"] == "reachable"
    assert payload["integration"]["probe"]["failure_stats"] == {
        "recent_failure_count": 2,
        "consecutive_failure_count": 0,
    }


def test_ops_summary_payload_guides_network_triage_from_probe_kind() -> None:
    class FakeGatewayClient:
        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": None, "kind": "network_error", "message": "Unable to reach OpenClaw gateway."}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 300,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
        }
    )
    runner._gateway_client = FakeGatewayClient()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 40, 0))
    finally:
        runner.stop()

    assert payload["operator_guidance"]["action"] == "check_network"
    assert "DNS" in payload["operator_guidance"]["rationale"]


def test_ops_summary_payload_guides_4xx_triage_from_probe_kind() -> None:
    class FakeRuntimeBridge:
        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 405, "kind": "http_4xx", "message": "405 from runtime invoke endpoint."}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 300,
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._dispatcher.runtime_bridge = FakeRuntimeBridge()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 41, 0))
    finally:
        runner.stop()

    assert payload["operator_guidance"]["action"] == "check_integration_config"
    assert "token" in payload["operator_guidance"]["rationale"]


def test_ops_summary_payload_guides_5xx_triage_from_probe_kind() -> None:
    class FakeRuntimeBridge:
        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": 503, "kind": "http_5xx", "message": "503 from runtime invoke endpoint."}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 300,
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._dispatcher.runtime_bridge = FakeRuntimeBridge()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 42, 0))
    finally:
        runner.stop()

    assert payload["operator_guidance"]["action"] == "check_upstream_health"
    assert "上游服务健康" in payload["operator_guidance"]["rationale"]


def test_ops_summary_payload_guides_public_base_url_fix_when_hook_registration_is_missing() -> None:
    class FakeGatewayClient:
        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
        }
    )
    runner._gateway_client = FakeGatewayClient()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 3, 20, 0))
    finally:
        runner.stop()

    assert payload["operator_guidance"]["action"] == "configure_public_base_url"
    assert "OPENCLAW_PUBLIC_BASE_URL" in payload["operator_guidance"]["rationale"]


def test_ops_summary_payload_guides_gateway_registration_repair_when_registration_fails() -> None:
    class FailingGatewayClient:
        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("gateway offline")

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": None, "kind": "network_error", "message": "Unable to reach OpenClaw gateway."}

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
    runner._gateway_client = FailingGatewayClient()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 3, 21, 0))
    finally:
        runner.stop()

    assert payload["operator_guidance"]["action"] == "repair_hook_registration"
    assert "gateway offline" in payload["operator_guidance"]["rationale"]


def test_ops_summary_payload_surfaces_hook_registration_attention_in_intervention_summary() -> None:
    class FailingGatewayClient:
        def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("gateway offline")

        def probe_connectivity(self) -> dict[str, object]:
            return {"status": "unreachable", "ok": False, "status_code": None, "kind": "network_error", "message": "Unable to reach OpenClaw gateway."}

    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com/kernel",
            "hook_registration_retry_sec": 300,
        }
    )
    runner._gateway_client = FailingGatewayClient()  # type: ignore[assignment]

    try:
        runner.start()
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 5, 0, 0))
    finally:
        runner.stop()

    assert payload["intervention_summary"]["integration_attention"] == {
        "component": "gateway_hook_registration",
        "status": "register_failed",
        "attempt_count": 1,
        "next_retry_at": payload["intervention_summary"]["integration_attention"]["next_retry_at"],
        "message": "gateway offline",
    }


def test_ops_summary_payload_reuses_cached_probe_results_between_reads() -> None:
    class FakeGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def probe_connectivity(self) -> dict[str, object]:
            self.calls += 1
            return {"status": "reachable", "ok": True, "status_code": 200}

    class FakeRuntimeBridge:
        def __init__(self) -> None:
            self.calls = 0

        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            self.calls += 1
            return {"status": "reachable", "ok": True, "status_code": 204}

    gateway = FakeGatewayClient()
    runtime_bridge = FakeRuntimeBridge()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 300,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]
    runner._dispatcher.runtime_bridge = runtime_bridge  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 5, 0))
        second = runner.health_payload(now=datetime(2026, 3, 13, 2, 6, 0))
    finally:
        runner.stop()

    assert gateway.calls == 1
    assert runtime_bridge.calls == 1
    assert first["integration"]["probe"] == {
        "status": "reachable",
        "probed_at": "2026-03-13T02:05:00",
        "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        "gateway": {
            "status": "reachable",
            "ok": True,
            "status_code": 200,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        },
        "runtime_invoke": {
            "status": "reachable",
            "ok": True,
            "status_code": 204,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        },
    }
    assert second["integration"]["probe"] == first["integration"]["probe"]


def test_ops_summary_payload_refreshes_probe_after_ttl_expiry() -> None:
    class FakeGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def probe_connectivity(self) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {"status": "reachable", "ok": True, "status_code": 200}
            return {"status": "unreachable", "ok": False, "status_code": 503}

    class FakeRuntimeBridge:
        def __init__(self) -> None:
            self.calls = 0

        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {"status": "reachable", "ok": True, "status_code": 204}
            return {"status": "unreachable", "ok": False, "status_code": 504}

    gateway = FakeGatewayClient()
    runtime_bridge = FakeRuntimeBridge()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 30,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]
    runner._dispatcher.runtime_bridge = runtime_bridge  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 20, 0))
        second = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 20, 20))
        third = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 20, 31))
    finally:
        runner.stop()

    assert gateway.calls == 2
    assert runtime_bridge.calls == 2
    assert first["integration"]["probe"] == {
        "status": "reachable",
        "probed_at": "2026-03-13T02:20:00",
        "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        "gateway": {
            "status": "reachable",
            "ok": True,
            "status_code": 200,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        },
        "runtime_invoke": {
            "status": "reachable",
            "ok": True,
            "status_code": 204,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        },
    }
    assert second["integration"]["probe"] == first["integration"]["probe"]
    assert third["integration"]["probe"] == {
        "status": "unreachable",
        "probed_at": "2026-03-13T02:20:31",
        "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        "gateway": {
            "status": "unreachable",
            "ok": False,
            "status_code": 503,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        },
        "runtime_invoke": {
            "status": "unreachable",
            "ok": False,
            "status_code": 504,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        },
    }


def test_maintenance_cycle_refreshes_cached_probe_results() -> None:
    class FakeGatewayClient:
        def __init__(self) -> None:
            self.calls = 0

        def probe_connectivity(self) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {"status": "reachable", "ok": True, "status_code": 200}
            return {"status": "unreachable", "ok": False, "status_code": 503}

    class FakeRuntimeBridge:
        def __init__(self) -> None:
            self.calls = 0

        def submit_invoke(self, payload: dict[str, object]) -> dict[str, object]:
            return {"accepted": True, "status_code": 202, "response": payload}

        def probe_connectivity(self) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {"status": "reachable", "ok": True, "status_code": 204}
            return {"status": "unreachable", "ok": False, "status_code": 504}

    gateway = FakeGatewayClient()
    runtime_bridge = FakeRuntimeBridge()
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "integration_probe_ttl_sec": 300,
            "gateway_base_url": "http://127.0.0.1:18789",
            "hooks_token": "hook-secret",
            "runtime_invoke_url": "http://127.0.0.1:18789/runtime/invoke",
        }
    )
    runner._gateway_client = gateway  # type: ignore[assignment]
    runner._dispatcher.runtime_bridge = runtime_bridge  # type: ignore[assignment]

    try:
        runner.start()
        first = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 10, 0))
        runner.run_maintenance_cycle(now=datetime(2026, 3, 13, 2, 15, 0))
        second = runner.ops_summary_payload(now=datetime(2026, 3, 13, 2, 16, 0))
    finally:
        runner.stop()

    assert gateway.calls == 2
    assert runtime_bridge.calls == 2
    assert first["integration"]["probe"] == {
        "status": "reachable",
        "probed_at": "2026-03-13T02:10:00",
        "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        "gateway": {
            "status": "reachable",
            "ok": True,
            "status_code": 200,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        },
        "runtime_invoke": {
            "status": "reachable",
            "ok": True,
            "status_code": 204,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 0, "consecutive_failure_count": 0},
        },
    }
    assert second["integration"]["probe"] == {
        "status": "unreachable",
        "probed_at": "2026-03-13T02:15:00",
        "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        "gateway": {
            "status": "unreachable",
            "ok": False,
            "status_code": 503,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        },
        "runtime_invoke": {
            "status": "unreachable",
            "ok": False,
            "status_code": 504,
            "kind": None,
            "message": None,
            "failure_stats": {"recent_failure_count": 1, "consecutive_failure_count": 1},
        },
    }


def test_ops_summary_payload_marks_maintenance_as_in_progress_when_recent_cycle_had_actions() -> None:
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
        task_id = _create_task(runner, request_id="req-service-runner-ops-summary-maintenance-effect")
        update_task_fields(
            conn,
            task_id,
            blocked=1,
            block_reason="waiting human input",
            block_since=(utc_now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        runner.run_maintenance_cycle(now=utc_now())

        payload = runner.ops_summary_payload(now=utc_now())
    finally:
        runner.stop()

    assert payload["intervention_summary"]["priority_category"] == "blocked"
    assert payload["intervention_summary"]["maintenance_effectiveness"] == "in_progress"
    assert payload["intervention_summary"]["resolved_categories"] == []
    assert payload["intervention_summary"]["unresolved_categories"] == ["blocked"]
    assert payload["intervention_summary"]["resolved_task_ids"] == []
    assert payload["intervention_summary"]["attention_tasks"] == [{"task_id": task_id, "category": "blocked"}]
    assert payload["intervention_summary"]["attention_reason"] == "Priority focus is blocked because maintenance has started acting on it, but the anomaly remains active."


def test_ops_summary_payload_reports_resolved_timeout_categories_after_maintenance() -> None:
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
            "executing_timeout_sec": 60,
        }
    )
    conn = runner._app.conn
    assert conn is not None

    try:
        runner.start()
        task_id = _create_task(runner, request_id="req-service-runner-ops-summary-resolved-timeout")
        update_task_fields(
            conn,
            task_id,
            state="executing",
            current_role="executor",
            dispatch_status="running",
            dispatch_role="executor",
            dispatch_started_at="2026-03-13 00:00:00",
        )

        runner.run_maintenance_cycle(now=datetime(2026, 3, 13, 1, 0, 0))
        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 1, 0, 0))
    finally:
        runner.stop()

    assert payload["anomalies"]["total_count"] == 0
    assert payload["intervention_summary"]["resolved_categories"] == ["execution_timeout"]
    assert payload["intervention_summary"]["unresolved_categories"] == []
    assert payload["intervention_summary"]["resolved_task_ids"] == [task_id]
    assert payload["intervention_summary"]["attention_tasks"] == []
    assert payload["intervention_summary"]["maintenance_effectiveness"] == "healthy"
    assert payload["intervention_summary"]["attention_reason"] == "Recent maintenance resolved previously detected execution_timeout anomalies."
    assert payload["maintenance"]["trend"]["recent_cycle_count"] == 1
    assert payload["maintenance"]["trend"]["last_effective_cycle_started_at"] == "2026-03-13T01:00:00"
    assert payload["maintenance"]["trend"]["recently_resolved_categories"] == ["execution_timeout"]
    assert payload["maintenance"]["trend"]["recently_resolved_task_ids"] == [task_id]


def test_ops_summary_payload_summarizes_recent_maintenance_trends() -> None:
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
        runner.run_maintenance_cycle(now=datetime(2026, 3, 13, 0, 0, 0))

        task_id = _create_task(runner, request_id="req-service-runner-ops-summary-trend")
        update_task_fields(
            conn,
            task_id,
            blocked=1,
            block_reason="waiting human input",
            block_since="2026-03-12 23:40:00",
        )
        runner.run_maintenance_cycle(now=datetime(2026, 3, 13, 0, 10, 0))

        payload = runner.ops_summary_payload(now=datetime(2026, 3, 13, 0, 10, 0))
    finally:
        runner.stop()

    trend = payload["maintenance"]["trend"]
    assert trend["recent_cycle_count"] == 2
    assert trend["latest_cycle_started_at"] == "2026-03-13T00:10:00"
    assert trend["consecutive_no_effect_cycles"] == 0
    assert trend["consecutive_in_progress_cycles"] == 1
    assert trend["last_effective_cycle_started_at"] == "2026-03-13T00:10:00"
    assert trend["recently_resolved_categories"] == []
    assert trend["recently_resolved_task_ids"] == []


def test_ops_summary_endpoint_returns_aggregated_runner_state() -> None:
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
        _create_task(runner, request_id="req-service-runner-ops-summary-endpoint")
        runner.run_maintenance_cycle(now=utc_now())
        assert runner.http_service.base_url is not None

        with urlopen(f"{runner.http_service.base_url}/ops/summary") as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        runner.stop()

    assert body["status"] == "ok"
    assert body["ops"]["lifecycle_state"] == "ready"
    assert body["ops"]["health"]["status"] == "ok"
    assert body["ops"]["integration"]["status"] == "local_only"
    assert body["ops"]["integration"]["probe"]["status"] == "not_configured"
    assert body["ops"]["readiness"]["status"] == "ready"
    assert body["ops"]["maintenance"]["last_cycle"] is not None
    assert "trend" in body["ops"]["maintenance"]
    assert "anomalies" in body["ops"]
    assert "operator_guidance" in body["ops"]
    assert "intervention_summary" in body["ops"]
    assert "attention_tasks" in body["ops"]["intervention_summary"]
