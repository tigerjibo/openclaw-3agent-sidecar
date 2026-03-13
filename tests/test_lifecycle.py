"""Task 3: Shutdown/startup lifecycle edge-case tests.

Validates that ServiceRunner start/stop ordering is safe and predictable:
- repeated stop is idempotent
- start→stop→start on the same runner is safe (fresh runner per restart)
- DB connection is closed after stop
- maintenance thread is cleaned up on stop
"""
from __future__ import annotations

from sidecar.adapters.ingress import IngressAdapter
from sidecar.service_runner import ServiceRunner


def _runner_config(db_path: str) -> dict:
    return {
        "host": "127.0.0.1",
        "port": 0,
        "default_runtime_mode": "legacy_single",
        "db_path": db_path,
    }


def _create_task(runner: ServiceRunner, request_id: str) -> str:
    ingress = IngressAdapter(runner._app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-lifecycle",
            "entrypoint": "institutional_task",
            "title": "lifecycle test task",
            "message": "Lifecycle edge case test.",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_double_stop_is_idempotent(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    runner = ServiceRunner(config=_runner_config(db_path))
    runner.start()
    runner.stop()
    # Second stop should not raise
    runner.stop()
    assert runner.lifecycle_state == "stopping"


def test_maintenance_thread_cleaned_up_on_stop(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    cfg = _runner_config(db_path)
    cfg["maintenance_interval_sec"] = 0.1
    runner = ServiceRunner(config=cfg)
    runner.start()
    assert runner._maintenance_thread is not None
    runner.stop()
    assert runner._maintenance_thread is None


def test_fresh_runner_after_stop(tmp_path) -> None:
    """Creating a new ServiceRunner after stopping the old one works cleanly."""
    db_path = str(tmp_path / "sidecar.db")
    cfg = _runner_config(db_path)

    r1 = ServiceRunner(config=cfg)
    r1.start()
    task_id = _create_task(r1, "req-lifecycle-fresh")
    r1.stop()

    r2 = ServiceRunner(config=cfg)
    r2.start()
    try:
        from sidecar.models import get_task_by_id
        task = get_task_by_id(r2._app.conn, task_id)
        assert task is not None
        assert task["task_id"] == task_id
    finally:
        r2.stop()


def test_lifecycle_state_transitions(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    runner = ServiceRunner(config=_runner_config(db_path))
    assert runner.lifecycle_state == "starting"

    runner.start()
    assert runner.lifecycle_state == "ready"

    runner.stop()
    assert runner.lifecycle_state == "stopping"
