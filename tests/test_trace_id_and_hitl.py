"""Task 5: Trace ID propagation and HITL unblock endpoint tests."""
from __future__ import annotations

import json
import urllib.request

from sidecar.adapters.agent_invoke import AgentInvokeAdapter
from sidecar.adapters.ingress import IngressAdapter
from sidecar.adapters.result import ResultAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.events import list_recent_events
from sidecar.models import get_task_by_id, mark_task_blocked
from sidecar.runtime_mode import RuntimeModeController
from sidecar.service_runner import ServiceRunner
from sidecar.storage import connect, init_db


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def _ingest_task(app: TaskKernelApiApp, request_id: str = "req-trace") -> str:
    ingress = IngressAdapter(app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-trace",
            "entrypoint": "institutional_task",
            "title": "trace test task",
            "message": "Trace ID test.",
            "task_type_hint": "engineering",
        }
    )["task_id"]


# ---------- Trace ID propagation ----------

def test_ingress_generates_trace_id() -> None:
    app = _build_app()
    task_id = _ingest_task(app, "req-trace-gen")
    task = get_task_by_id(app.conn, task_id)
    meta = json.loads(task["metadata_json"])
    assert "trace_id" in meta
    assert len(meta["trace_id"]) > 0


def test_ingress_propagates_provided_trace_id() -> None:
    app = _build_app()
    ingress = IngressAdapter(app)
    result = ingress.ingest(
        {
            "request_id": "req-trace-provided",
            "source": "feishu",
            "source_user_id": "user-trace",
            "entrypoint": "institutional_task",
            "title": "trace test task",
            "message": "Trace ID test.",
            "task_type_hint": "engineering",
            "trace_id": "custom-trace-123",
        }
    )
    task = get_task_by_id(app.conn, result["task_id"])
    meta = json.loads(task["metadata_json"])
    assert meta["trace_id"] == "custom-trace-123"


def test_invoke_payload_contains_trace_id() -> None:
    app = _build_app()
    task_id = _ingest_task(app, "req-trace-invoke")
    adapter = AgentInvokeAdapter(app)
    payload = adapter.build_invoke(task_id, role="coordinator")
    assert "trace_id" in payload
    assert len(payload["trace_id"]) > 0


def test_invoke_trace_id_matches_ingress_trace_id() -> None:
    app = _build_app()
    ingress = IngressAdapter(app)
    result = ingress.ingest(
        {
            "request_id": "req-trace-match",
            "source": "feishu",
            "source_user_id": "user-trace",
            "entrypoint": "institutional_task",
            "title": "trace test task",
            "message": "Trace ID test.",
            "task_type_hint": "engineering",
            "trace_id": "my-trace-abc",
        }
    )
    adapter = AgentInvokeAdapter(app)
    payload = adapter.build_invoke(result["task_id"], role="coordinator")
    assert payload["trace_id"] == "my-trace-abc"


def test_events_persist_trace_id() -> None:
    app = _build_app()
    task_id = _ingest_task(app, "req-trace-event")
    events = list_recent_events(app.conn, task_id, limit=10)

    assert events
    assert events[0]["trace_id"]


def test_result_callback_requires_trace_id() -> None:
    app = _build_app()
    task_id = _ingest_task(app, "req-trace-required")
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)
    invoke_payload = invoke.build_invoke(task_id, role="coordinator")

    try:
        result_adapter.apply_result(
            {
                "invoke_id": invoke_payload["invoke_id"],
                "task_id": task_id,
                "role": "coordinator",
                "status": "succeeded",
                "output": {
                    "goal": "should fail",
                    "acceptance_criteria": [],
                    "risk_notes": [],
                    "proposed_steps": [],
                },
            }
        )
    except ValueError as exc:
        assert "trace_id is required" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected trace_id validation failure")


# ---------- HITL unblock HTTP endpoint ----------

def test_http_unblock_endpoint(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    runner = ServiceRunner(config={
        "host": "127.0.0.1",
        "port": 0,
        "default_runtime_mode": "legacy_single",
        "db_path": db_path,
    })
    runner.start()
    try:
        task_id = _ingest_task(runner._app, "req-unblock-http")
        mark_task_blocked(runner._app.conn, task_id, reason="needs info")
        runner._app.conn.commit()

        task = get_task_by_id(runner._app.conn, task_id)
        assert task["blocked"] == 1

        url = f"{runner.http_service.base_url}/runtime/unblock/{task_id}"
        req = urllib.request.Request(
            url,
            data=json.dumps({"actor_role": "human"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        assert body["ok"] is True
        task = get_task_by_id(runner._app.conn, task_id)
        assert task["blocked"] == 0
    finally:
        runner.stop()
