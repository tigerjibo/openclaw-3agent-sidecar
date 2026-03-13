from datetime import datetime, timedelta

from sidecar.adapters.ingress import IngressAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.events import list_recent_events
from sidecar.models import get_task_by_id, update_task_fields
from sidecar.runtime.dispatcher import TaskDispatcher
from sidecar.runtime.recovery import TaskRecovery
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def _create_task(app: TaskKernelApiApp, request_id: str = "req-recovery") -> str:
    ingress = IngressAdapter(app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-recovery",
            "entrypoint": "institutional_task",
            "title": "recovery test task",
            "message": "用于 recovery 测试。",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_recovery_releases_inflight_dispatch() -> None:
    app = _build_app()
    conn = app.conn
    assert conn is not None
    dispatcher = TaskDispatcher(app)
    recovery = TaskRecovery(app)
    task_id = _create_task(app, request_id="req-recovery-inflight")

    dispatcher.dispatch_task(task_id)

    recovered = recovery.recover_inflight_dispatches()
    task = get_task_by_id(conn, task_id)
    events = list_recent_events(conn, task_id, limit=10)

    assert recovered == [task_id]
    assert task is not None
    assert task["dispatch_status"] == "idle"
    assert task["dispatch_role"] is None
    assert any(e["event_type"] == "task.recovered" and e["action"] == "recover_dispatch" for e in events)


def test_recovery_handles_execution_timeout() -> None:
    app = _build_app()
    conn = app.conn
    assert conn is not None
    recovery = TaskRecovery(app, executing_timeout_sec=3600)
    task_id = _create_task(app, request_id="req-recovery-exec-timeout")

    update_task_fields(
        conn,
        task_id,
        state="executing",
        current_role="executor",
        dispatch_status="running",
        dispatch_role="executor",
        dispatch_started_at=(datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    recovered = recovery.recover_execution_timeouts(now=datetime.utcnow())
    task = get_task_by_id(conn, task_id)
    events = list_recent_events(conn, task_id, limit=10)

    assert recovered == [task_id]
    assert task is not None
    assert task["dispatch_status"] == "idle"
    assert any(e["event_type"] == "task.recovered" and e["action"] == "escalate_timeout" for e in events)


def test_recovery_handles_review_timeout() -> None:
    app = _build_app()
    conn = app.conn
    assert conn is not None
    recovery = TaskRecovery(app, reviewing_timeout_sec=3600)
    task_id = _create_task(app, request_id="req-recovery-review-timeout")

    update_task_fields(
        conn,
        task_id,
        state="reviewing",
        current_role="reviewer",
        dispatch_status="running",
        dispatch_role="reviewer",
        dispatch_started_at=(datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    recovered = recovery.recover_review_timeouts(now=datetime.utcnow())
    task = get_task_by_id(conn, task_id)
    events = list_recent_events(conn, task_id, limit=10)

    assert recovered == [task_id]
    assert task is not None
    assert task["dispatch_status"] == "idle"
    assert any(e["event_type"] == "task.recovered" and e["action"] == "escalate_timeout" for e in events)


def test_recovery_escalates_long_blocked_task() -> None:
    app = _build_app()
    conn = app.conn
    assert conn is not None
    recovery = TaskRecovery(app, blocked_alert_after_sec=3600)
    task_id = _create_task(app, request_id="req-recovery-blocked")

    update_task_fields(
        conn,
        task_id,
        blocked=1,
        block_reason="waiting external dependency",
        block_since=(datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    recovered = recovery.recover_blocked_tasks(now=datetime.utcnow())
    task = get_task_by_id(conn, task_id)
    events = list_recent_events(conn, task_id, limit=10)

    assert recovered == [task_id]
    assert task is not None
    assert task["blocked"] == 1
    assert any(e["event_type"] == "task.recovered" and e["action"] == "escalate_blocked" for e in events)


def test_recovery_run_once_returns_summary() -> None:
    app = _build_app()
    conn = app.conn
    assert conn is not None
    dispatcher = TaskDispatcher(app)
    recovery = TaskRecovery(
        app,
        executing_timeout_sec=3600,
        reviewing_timeout_sec=3600,
        blocked_alert_after_sec=3600,
    )

    inflight_id = _create_task(app, request_id="req-recovery-runonce-inflight")
    dispatcher.dispatch_task(inflight_id)

    exec_timeout_id = _create_task(app, request_id="req-recovery-runonce-exec")
    update_task_fields(
        conn,
        exec_timeout_id,
        state="executing",
        current_role="executor",
        dispatch_status="running",
        dispatch_role="executor",
        dispatch_started_at=(datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    review_timeout_id = _create_task(app, request_id="req-recovery-runonce-review")
    update_task_fields(
        conn,
        review_timeout_id,
        state="reviewing",
        current_role="reviewer",
        dispatch_status="running",
        dispatch_role="reviewer",
        dispatch_started_at=(datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    blocked_id = _create_task(app, request_id="req-recovery-runonce-blocked")
    update_task_fields(
        conn,
        blocked_id,
        blocked=1,
        block_reason="waiting external dependency",
        block_since=(datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    summary = recovery.run_once(now=datetime.utcnow())

    assert inflight_id in summary["recover_dispatch"]
    assert exec_timeout_id in summary["escalate_timeout"]
    assert review_timeout_id in summary["escalate_timeout"]
    assert blocked_id in summary["escalate_blocked"]
