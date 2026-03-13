from sidecar.adapters.ingress import IngressAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.models import get_task_by_id
from sidecar.runtime.dispatcher import TaskDispatcher
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def test_dispatcher_marks_task_running_and_prevents_duplicate_dispatch() -> None:
    app = _build_app()
    ingress = IngressAdapter(app)
    dispatcher = TaskDispatcher(app)
    task_id = ingress.ingest(
        {
            "request_id": "req-dispatch-001",
            "source": "feishu",
            "source_user_id": "user-dispatch",
            "entrypoint": "institutional_task",
            "title": "派发 coordinator",
            "message": "让 coordinator 先开始工作。",
            "task_type_hint": "engineering",
        }
    )["task_id"]

    first = dispatcher.dispatch_task(task_id)
    second = dispatcher.dispatch_task(task_id)

    assert first["dispatched"] is True
    assert first["invoke_payload"]["role"] == "coordinator"
    assert second["dispatched"] is False
    assert second["reason"] == "already_running"

    task = get_task_by_id(app.conn, task_id)
    assert task is not None
    assert task["dispatch_status"] == "running"
    assert task["dispatch_role"] == "coordinator"
    assert task["dispatch_attempts"] == 1
    assert task["last_invoke_id"] == first["invoke_payload"]["invoke_id"]
