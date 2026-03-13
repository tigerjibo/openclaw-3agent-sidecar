from __future__ import annotations

import threading

from sidecar.adapters.agent_invoke import AgentInvokeAdapter
from sidecar.adapters.ingress import IngressAdapter
from sidecar.adapters.result import ResultAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.events import list_recent_events
from sidecar.models import get_task_by_id
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


def _build_app(db_path: str) -> TaskKernelApiApp:
    conn = connect(db_path)
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def test_duplicate_result_is_safe_across_two_real_connections(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.sqlite3")
    app1 = _build_app(db_path)
    app2 = _build_app(db_path)
    conn1 = app1.conn
    conn2 = app2.conn
    assert conn1 is not None
    assert conn2 is not None

    ingress = IngressAdapter(app1)
    task_id = ingress.ingest(
        {
            "request_id": "req-concurrent-result",
            "source": "feishu",
            "source_user_id": "user-concurrent",
            "entrypoint": "institutional_task",
            "title": "concurrent result",
            "message": "real concurrent duplicate result test",
            "task_type_hint": "engineering",
        }
    )["task_id"]

    invoke = AgentInvokeAdapter(app1)
    coordinator_invoke = invoke.build_invoke(task_id, role="coordinator")
    payload = {
        "invoke_id": coordinator_invoke["invoke_id"],
        "task_id": task_id,
        "role": "coordinator",
        "trace_id": coordinator_invoke["trace_id"],
        "status": "succeeded",
        "output": {
            "goal": "concurrency",
            "acceptance_criteria": ["idempotent"],
            "risk_notes": [],
            "proposed_steps": [],
        },
    }

    results: list[dict] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def _worker(app: TaskKernelApiApp) -> None:
        try:
            barrier.wait(timeout=5)
            result = ResultAdapter(app).apply_result(dict(payload))
            results.append(result)
        except BaseException as exc:  # pragma: no cover - test helper
            errors.append(exc)

    t1 = threading.Thread(target=_worker, args=(app1,))
    t2 = threading.Thread(target=_worker, args=(app2,))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not errors
    assert len(results) == 2

    task = get_task_by_id(conn1, task_id)
    assert task is not None
    assert task["state"] == "queued"

    events = list_recent_events(conn1, task_id, limit=20)
    result_received_events = [
        event for event in events if event["event_type"] == "task.result_received" and event["idempotency_key"] == payload["invoke_id"]
    ]
    assert len(result_received_events) == 1

    conn1.close()
    conn2.close()
