from __future__ import annotations

import time
from datetime import datetime, timedelta

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
