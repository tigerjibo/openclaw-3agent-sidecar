from sidecar.adapters.ingress import IngressAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.models import list_tasks
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def test_ingress_creates_task_and_is_idempotent() -> None:
    app = _build_app()
    adapter = IngressAdapter(app)
    payload = {
        "request_id": "req-20260313-001",
        "source": "feishu",
        "source_message_id": "msg-001",
        "source_user_id": "user-123",
        "source_chat_id": "chat-456",
        "entrypoint": "institutional_task",
        "title": "设计注册系统",
        "message": "请设计一个用户注册系统，包含 API、数据库、JWT、测试。",
        "task_type_hint": "engineering",
        "priority_hint": "normal",
        "risk_level_hint": "normal",
        "metadata": {"channel": "feishu", "deliver_back": True},
    }

    first = adapter.ingest(payload)
    second = adapter.ingest(payload)

    assert first["created"] is True
    assert second["created"] is False
    assert first["task_id"] == second["task_id"]

    tasks = list_tasks(app.conn)
    assert len(tasks) == 1
    assert tasks[0]["title"] == "设计注册系统"
    assert tasks[0]["task_type"] == "engineering"
    assert tasks[0]["source"] == "feishu"
    assert tasks[0]["created_by"] == "user-123"
    assert tasks[0]["state"] == "inbox"
