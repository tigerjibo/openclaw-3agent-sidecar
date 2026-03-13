"""Task 1: Restart consistency test matrix.

Validates that after a ServiceRunner restart (persistent DB, new process),
recovery, dispatch, timeout, and blocked handling all behave correctly.
"""
from __future__ import annotations

from datetime import timedelta

from sidecar.adapters.ingress import IngressAdapter
from sidecar.models import get_task_by_id, update_task_fields
from sidecar.service_runner import ServiceRunner
from sidecar.time_utils import utc_now


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
            "source_user_id": "user-restart",
            "entrypoint": "institutional_task",
            "title": "restart test task",
            "message": "Restart consistency test.",
            "task_type_hint": "engineering",
        }
    )["task_id"]


# -------------------------------------------------------------------
# Scenario 1: dispatch_status=running tasks are recovered after restart
# -------------------------------------------------------------------
def test_restart_recovers_inflight_dispatch(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    cfg = _runner_config(db_path)

    # First runner: create task and dispatch
    r1 = ServiceRunner(config=cfg)
    r1.start()
    try:
        task_id = _create_task(r1, "req-restart-inflight")
        r1._dispatcher.dispatch_task(task_id)
        task = get_task_by_id(r1._app.conn, task_id)
        assert task["dispatch_status"] == "running"
    finally:
        r1.stop()

    # Second runner: recovery should release the inflight dispatch
    r2 = ServiceRunner(config=cfg)
    r2.start()
    try:
        summary = r2._recovery.run_once(now=utc_now())
        assert task_id in summary["recover_dispatch"]
        task = get_task_by_id(r2._app.conn, task_id)
        assert task["dispatch_status"] == "idle"
        assert task["dispatch_role"] is None
    finally:
        r2.stop()


# -------------------------------------------------------------------
# Scenario 2: timeout tasks are escalated exactly once after restart
# -------------------------------------------------------------------
def test_restart_escalates_execution_timeout_once(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    cfg = _runner_config(db_path)

    r1 = ServiceRunner(config=cfg)
    r1.start()
    try:
        task_id = _create_task(r1, "req-restart-exec-timeout")
        update_task_fields(
            r1._app.conn,
            task_id,
            state="executing",
            current_role="executor",
            dispatch_status="running",
            dispatch_role="executor",
            dispatch_started_at=(utc_now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        r1._app.conn.commit()
    finally:
        r1.stop()

    r2 = ServiceRunner(config=cfg)
    r2.start()
    try:
        summary1 = r2._recovery.run_once(now=utc_now())
        assert task_id in summary1["escalate_timeout"]

        # Second run should NOT re-escalate (dispatch already reset to idle)
        summary2 = r2._recovery.run_once(now=utc_now())
        assert task_id not in summary2["escalate_timeout"]
    finally:
        r2.stop()


# -------------------------------------------------------------------
# Scenario 3: blocked tasks remain identified after restart
# -------------------------------------------------------------------
def test_restart_blocked_task_still_detected(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    cfg = _runner_config(db_path)

    r1 = ServiceRunner(config=cfg)
    r1.start()
    try:
        task_id = _create_task(r1, "req-restart-blocked")
        update_task_fields(
            r1._app.conn,
            task_id,
            blocked=1,
            block_reason="external dependency",
            block_since=(utc_now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
        )
        r1._app.conn.commit()
    finally:
        r1.stop()

    r2 = ServiceRunner(config=cfg)
    r2.start()
    try:
        summary = r2._recovery.run_once(now=utc_now())
        assert task_id in summary["escalate_blocked"]

        task = get_task_by_id(r2._app.conn, task_id)
        assert task["blocked"] == 1
        assert task["block_reason"] == "external dependency"
    finally:
        r2.stop()


# -------------------------------------------------------------------
# Scenario 4: maintenance cycle runs cleanly after restart
# -------------------------------------------------------------------
def test_restart_maintenance_cycle_runs_clean(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    cfg = _runner_config(db_path)

    r1 = ServiceRunner(config=cfg)
    r1.start()
    try:
        _create_task(r1, "req-restart-maintenance")
    finally:
        r1.stop()

    r2 = ServiceRunner(config=cfg)
    r2.start()
    try:
        summary = r2.run_maintenance_cycle(now=utc_now())
        assert "recovery" in summary
        assert "dispatched_count" in summary
    finally:
        r2.stop()


# -------------------------------------------------------------------
# Scenario 5: health/readiness reflects correct state after restart
# -------------------------------------------------------------------
def test_restart_health_readiness_correct(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    cfg = _runner_config(db_path)

    r1 = ServiceRunner(config=cfg)
    r1.start()
    try:
        _create_task(r1, "req-restart-health")
    finally:
        r1.stop()

    r2 = ServiceRunner(config=cfg)
    r2.start()
    try:
        health = r2.health_payload(now=utc_now())
        readiness = r2.readiness_payload()
        assert health["status"] in ("ok", "degraded")
        assert readiness["status"] in ("ready", "warming", "blocked")
    finally:
        r2.stop()


# -------------------------------------------------------------------
# Scenario 6: scheduler dispatches ready tasks after restart
# -------------------------------------------------------------------
def test_restart_scheduler_dispatches_ready_tasks(tmp_path) -> None:
    db_path = str(tmp_path / "sidecar.db")
    cfg = _runner_config(db_path)

    r1 = ServiceRunner(config=cfg)
    r1.start()
    try:
        task_id = _create_task(r1, "req-restart-scheduler")
        # Task is in inbox with current_role=coordinator, dispatch_status=idle
        # Should be dispatchable by scheduler
    finally:
        r1.stop()

    r2 = ServiceRunner(config=cfg)
    r2.start()
    try:
        dispatched = r2._scheduler.dispatch_ready_tasks(limit=10)
        dispatched_ids = [d["task_id"] for d in dispatched]
        assert task_id in dispatched_ids
    finally:
        r2.stop()
