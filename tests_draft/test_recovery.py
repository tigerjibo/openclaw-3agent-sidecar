"""Draft recovery tests for the next implementation phase.

These tests are intentionally placed outside the active pytest `testpaths`
so the current green baseline is preserved. When implementation starts,
move or copy them into `tests/test_recovery.py` and run them as RED tests.
"""

from datetime import datetime, timedelta

from sidecar.adapters.ingress import IngressAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.models import get_task_by_id, update_task_fields
from sidecar.runtime.dispatcher import TaskDispatcher
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


# NOTE:
# The import below is intentionally commented until recovery.py exists.
# from sidecar.runtime.recovery import TaskRecovery


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def _create_task(app: TaskKernelApiApp, request_id: str = "req-recovery-draft") -> str:
    ingress = IngressAdapter(app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-recovery",
            "entrypoint": "institutional_task",
            "title": "recovery draft task",
            "message": "用于 recovery 草稿测试。",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_draft_recovery_releases_inflight_dispatch() -> None:
    app = _build_app()
    dispatcher = TaskDispatcher(app)
    task_id = _create_task(app, request_id="req-recovery-inflight")

    dispatcher.dispatch_task(task_id)

    # recovery = TaskRecovery(app)
    # recovered = recovery.recover_inflight_dispatches()
    # task = get_task_by_id(app.conn, task_id)
    # assert recovered == [task_id]
    # assert task is not None
    # assert task["dispatch_status"] == "idle"
    # assert task["dispatch_role"] is None


def test_draft_recovery_handles_execution_timeout() -> None:
    app = _build_app()
    task_id = _create_task(app, request_id="req-recovery-exec-timeout")

    update_task_fields(
        app.conn,
        task_id,
        state="executing",
        current_role="executor",
        dispatch_status="running",
        dispatch_role="executor",
        dispatch_started_at=(datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    # recovery = TaskRecovery(app)
    # recovered = recovery.recover_execution_timeouts(now=datetime.utcnow())
    # task = get_task_by_id(app.conn, task_id)
    # assert recovered == [task_id]
    # assert task is not None
    # assert task["dispatch_status"] == "idle"


def test_draft_recovery_handles_review_timeout() -> None:
    app = _build_app()
    task_id = _create_task(app, request_id="req-recovery-review-timeout")

    update_task_fields(
        app.conn,
        task_id,
        state="reviewing",
        current_role="reviewer",
        dispatch_status="running",
        dispatch_role="reviewer",
        dispatch_started_at=(datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    # recovery = TaskRecovery(app)
    # recovered = recovery.recover_review_timeouts(now=datetime.utcnow())
    # task = get_task_by_id(app.conn, task_id)
    # assert recovered == [task_id]
    # assert task is not None
    # assert task["dispatch_status"] == "idle"


def test_draft_recovery_escalates_long_blocked_task() -> None:
    app = _build_app()
    task_id = _create_task(app, request_id="req-recovery-blocked")

    update_task_fields(
        app.conn,
        task_id,
        blocked=1,
        block_reason="waiting external dependency",
        block_since=(datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    # recovery = TaskRecovery(app)
    # recovered = recovery.recover_blocked_tasks(now=datetime.utcnow())
    # assert recovered == [task_id]
    # task = get_task_by_id(app.conn, task_id)
    # assert task is not None
    # assert task["blocked"] == 1
