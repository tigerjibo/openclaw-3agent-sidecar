from sidecar.adapters.ingress import IngressAdapter
from sidecar.adapters.result import ResultAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.events import list_recent_events
from sidecar.models import get_task_by_id
from sidecar.runtime.dispatcher import TaskDispatcher
from sidecar.runtime.scheduler import TaskScheduler
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def test_scheduler_recovers_inflight_dispatch_and_allows_redispatch() -> None:
    app = _build_app()
    ingress = IngressAdapter(app)
    dispatcher = TaskDispatcher(app)
    scheduler = TaskScheduler(app, dispatcher=dispatcher)

    task_id = ingress.ingest(
        {
            "request_id": "req-scheduler-001",
            "source": "feishu",
            "source_user_id": "user-scheduler",
            "entrypoint": "institutional_task",
            "title": "恢复未完成派发",
            "message": "模拟服务重启后的恢复。",
            "task_type_hint": "engineering",
        }
    )["task_id"]

    first = dispatcher.dispatch_task(task_id)
    assert first["dispatched"] is True

    recovered = scheduler.recover_inflight_tasks()
    task = get_task_by_id(app.conn, task_id)

    assert recovered == [task_id]
    assert task is not None
    assert task["dispatch_status"] == "idle"
    assert task["dispatch_role"] is None

    second = dispatcher.dispatch_task(task_id)
    task_after = get_task_by_id(app.conn, task_id)

    assert second["dispatched"] is True
    assert task_after is not None
    assert task_after["dispatch_attempts"] == 2


def test_scheduler_dispatches_ready_task_after_state_progression() -> None:
    app = _build_app()
    ingress = IngressAdapter(app)
    dispatcher = TaskDispatcher(app)
    scheduler = TaskScheduler(app, dispatcher=dispatcher)
    result_adapter = ResultAdapter(app)

    task_id = ingress.ingest(
        {
            "request_id": "req-scheduler-002",
            "source": "feishu",
            "source_user_id": "user-ready",
            "entrypoint": "institutional_task",
            "title": "自动推进到 executor",
            "message": "先 coordinator，再 scheduler 派 executor。",
            "task_type_hint": "engineering",
        }
    )["task_id"]

    first_dispatch = dispatcher.dispatch_task(task_id)
    result_adapter.apply_result(
        {
            "invoke_id": first_dispatch["invoke_payload"]["invoke_id"],
            "task_id": task_id,
            "role": "coordinator",
            "trace_id": first_dispatch["invoke_payload"]["trace_id"],
            "status": "succeeded",
            "output": {
                "goal": "自动推进",
                "acceptance_criteria": ["到 queued"],
                "risk_notes": [],
                "proposed_steps": ["executor 执行"],
            },
        }
    )

    dispatched = scheduler.dispatch_ready_tasks(limit=10)
    task = get_task_by_id(app.conn, task_id)
    events = list_recent_events(app.conn, task_id, limit=20)

    assert len(dispatched) == 1
    assert dispatched[0]["invoke_payload"]["role"] == "executor"
    assert task is not None
    assert task["dispatch_status"] == "running"
    assert task["dispatch_role"] == "executor"
    assert any(event["event_type"] == "task.dispatched" for event in events)
