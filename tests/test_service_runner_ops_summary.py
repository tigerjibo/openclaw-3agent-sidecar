from __future__ import annotations

import json
from datetime import datetime
from urllib.request import urlopen

from sidecar.adapters.ingress import IngressAdapter
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
    assert task_id in payload["maintenance"]["last_cycle"]["dispatched_task_ids"]


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
