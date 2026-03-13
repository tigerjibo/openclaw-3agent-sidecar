from __future__ import annotations

import json
from datetime import datetime, timedelta
from urllib.request import urlopen

from sidecar.adapters.ingress import IngressAdapter
from sidecar.models import update_task_fields
from sidecar.service_runner import ServiceRunner


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
        runner.run_maintenance_cycle(now=datetime.utcnow())
        payload = runner.ops_summary_payload(now=datetime.utcnow())
    finally:
        runner.stop()

    assert payload["status"] == "ok"
    assert payload["lifecycle_state"] == "ready"
    assert payload["health"]["status"] == "ok"
    assert payload["readiness"]["status"] == "ready"
    assert payload["maintenance"]["last_cycle"] is not None
    assert payload["anomalies"]["total_count"] == 0
    assert payload["operator_guidance"]["action"] == "observe"
    assert payload["intervention_summary"]["priority_category"] is None
    assert payload["intervention_summary"]["attention_task_ids"] == []
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
            block_since=(datetime.utcnow() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        )

        payload = runner.ops_summary_payload(now=datetime.utcnow())
    finally:
        runner.stop()

    assert payload["anomalies"]["total_count"] == 1
    assert payload["anomalies"]["by_category"]["blocked"] == 1
    assert task_id in payload["anomalies"]["items"][0]["task_ids"]
    assert payload["operator_guidance"]["action"] == "investigate"
    assert payload["intervention_summary"]["priority_category"] == "blocked"
    assert payload["intervention_summary"]["attention_task_ids"] == [task_id]
    assert payload["intervention_summary"]["maintenance_effectiveness"] == "no_recent_maintenance"


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
    assert payload["operator_guidance"]["action"] == "manual_intervention"
    assert payload["intervention_summary"]["priority_category"] is None


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
            block_since=(datetime.utcnow() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        runner.run_maintenance_cycle(now=datetime.utcnow())

        payload = runner.ops_summary_payload(now=datetime.utcnow())
    finally:
        runner.stop()

    assert payload["intervention_summary"]["priority_category"] == "blocked"
    assert payload["intervention_summary"]["maintenance_effectiveness"] == "in_progress"


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
        runner.run_maintenance_cycle(now=datetime.utcnow())
        assert runner.http_service.base_url is not None

        with urlopen(f"{runner.http_service.base_url}/ops/summary") as response:
            body = json.loads(response.read().decode("utf-8"))
    finally:
        runner.stop()

    assert body["status"] == "ok"
    assert body["ops"]["lifecycle_state"] == "ready"
    assert body["ops"]["health"]["status"] == "ok"
    assert body["ops"]["readiness"]["status"] == "ready"
    assert body["ops"]["maintenance"]["last_cycle"] is not None
    assert "anomalies" in body["ops"]
    assert "operator_guidance" in body["ops"]
    assert "intervention_summary" in body["ops"]
