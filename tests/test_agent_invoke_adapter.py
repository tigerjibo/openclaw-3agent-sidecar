from sidecar.adapters.agent_invoke import AgentInvokeAdapter
from sidecar.adapters.ingress import IngressAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def test_agent_invoke_builds_stable_payload_for_role() -> None:
    app = _build_app()
    ingress = IngressAdapter(app)
    invoke = AgentInvokeAdapter(app)

    ingest_result = ingress.ingest(
        {
            "request_id": "req-20260313-002",
            "source": "feishu",
            "source_user_id": "user-007",
            "entrypoint": "institutional_task",
            "title": "设计支付系统",
            "message": "请设计一个支持退款和对账的支付系统。",
            "task_type_hint": "architecture",
        }
    )

    payload = invoke.build_invoke(ingest_result["task_id"], role="coordinator")

    assert payload["task_id"] == ingest_result["task_id"]
    assert payload["role"] == "coordinator"
    assert payload["agent_id"] == "coordinator"
    assert payload["session_key"] == f"task:{ingest_result['task_id']}:coordinator"
    assert payload["invoke_id"].startswith(f"inv:{ingest_result['task_id']}:coordinator:v")
    assert payload["goal"]
    assert payload["input"]["title"] == "设计支付系统"
    assert payload["input"]["message"] == "请设计一个支持退款和对账的支付系统。"
    assert payload["input"]["task_context"]["state"] == "inbox"
    assert payload["constraints"]["structured_output_required"] is True
