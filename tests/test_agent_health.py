from datetime import timedelta

from sidecar.adapters.ingress import IngressAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.models import update_task_fields
from sidecar.runtime.agent_health import AgentHealthMonitor
from sidecar.runtime.dispatcher import TaskDispatcher
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db
from sidecar.time_utils import utc_now


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def _create_task(app: TaskKernelApiApp, request_id: str) -> str:
    ingress = IngressAdapter(app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-agent-health",
            "entrypoint": "institutional_task",
            "title": "agent health task",
            "message": "用于 agent health 测试。",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_agent_health_reports_ok_when_no_running_dispatch() -> None:
    app = _build_app()
    monitor = AgentHealthMonitor(app, stale_after_sec=300)

    snapshot = monitor.snapshot(now=utc_now())

    assert snapshot["status"] == "ok"
    assert snapshot["running_dispatch_count"] == 0
    assert snapshot["stale_dispatch_task_ids"] == []
    assert snapshot["roles"]["coordinator"]["status"] == "idle"
    assert snapshot["roles"]["executor"]["status"] == "idle"
    assert snapshot["roles"]["reviewer"]["status"] == "idle"


def test_agent_health_reports_running_for_recent_dispatch() -> None:
    app = _build_app()
    dispatcher = TaskDispatcher(app)
    monitor = AgentHealthMonitor(app, stale_after_sec=300)

    task_id = _create_task(app, request_id="req-agent-health-running")
    result = dispatcher.dispatch_task(task_id)

    assert result["dispatched"] is True

    snapshot = monitor.snapshot(now=utc_now())

    assert snapshot["status"] == "ok"
    assert snapshot["running_dispatch_count"] == 1
    assert snapshot["roles"]["coordinator"]["status"] == "running"
    assert snapshot["roles"]["coordinator"]["running_tasks"] == 1


def test_agent_health_reports_degraded_for_stale_dispatch() -> None:
    app = _build_app()
    conn = app.conn
    assert conn is not None
    monitor = AgentHealthMonitor(app, stale_after_sec=300)

    task_id = _create_task(app, request_id="req-agent-health-stale")
    update_task_fields(
        conn,
        task_id,
        state="executing",
        current_role="executor",
        dispatch_status="running",
        dispatch_role="executor",
        dispatch_started_at=(utc_now() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
    )

    snapshot = monitor.snapshot(now=utc_now())

    assert snapshot["status"] == "degraded"
    assert task_id in snapshot["stale_dispatch_task_ids"]
    assert snapshot["roles"]["executor"]["status"] == "degraded"
    assert task_id in snapshot["roles"]["executor"]["stale_task_ids"]
