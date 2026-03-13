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
            "source_user_id": "user-service-runner",
            "entrypoint": "institutional_task",
            "title": "service runner health task",
            "message": "用于 service runner health 测试。",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_service_runner_health_payload_includes_agent_health_snapshot() -> None:
    runner = ServiceRunner(config={"host": "127.0.0.1", "port": 0, "default_runtime_mode": "legacy_single"})

    try:
        runner.start()
        payload = runner.health_payload()
        agent_health = payload["agent_health"]
        assert isinstance(agent_health, dict)

        assert payload["status"] == "ok"
        assert agent_health["status"] == "ok"
        assert agent_health["running_dispatch_count"] == 0
    finally:
        runner.stop()


def test_service_runner_health_payload_degrades_for_stale_dispatch() -> None:
    runner = ServiceRunner(config={"host": "127.0.0.1", "port": 0, "default_runtime_mode": "legacy_single"})
    conn = runner._app.conn
    assert conn is not None

    try:
        runner.start()
        task_id = _create_task(runner, request_id="req-service-runner-stale")
        update_task_fields(
            conn,
            task_id,
            state="executing",
            current_role="executor",
            dispatch_status="running",
            dispatch_role="executor",
            dispatch_started_at=(datetime.utcnow() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
        )

        payload = runner.health_payload(now=datetime.utcnow())
        agent_health = payload["agent_health"]
        assert isinstance(agent_health, dict)

        assert payload["status"] == "degraded"
        assert agent_health["status"] == "degraded"
        assert task_id in agent_health["stale_dispatch_task_ids"]
    finally:
        runner.stop()


def test_healthz_endpoint_returns_agent_health_snapshot() -> None:
    runner = ServiceRunner(config={"host": "127.0.0.1", "port": 0, "default_runtime_mode": "legacy_single"})

    try:
        runner.start()
        assert runner.http_service.base_url is not None

        with urlopen(f"{runner.http_service.base_url}/healthz") as response:
            body = json.loads(response.read().decode("utf-8"))

        assert body["status"] == "ok"
        assert body["agent_health"]["status"] == "ok"
        assert "roles" in body["agent_health"]
    finally:
        runner.stop()
