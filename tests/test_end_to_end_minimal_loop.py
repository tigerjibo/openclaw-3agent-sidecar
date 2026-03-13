from sidecar.adapters.agent_invoke import AgentInvokeAdapter
from sidecar.adapters.ingress import IngressAdapter
from sidecar.adapters.result import ResultAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.events import list_recent_events
from sidecar.models import get_task_by_id
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def test_end_to_end_minimal_adapter_loop_reaches_done() -> None:
    app = _build_app()
    ingress = IngressAdapter(app)
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)

    ingest_result = ingress.ingest(
        {
            "request_id": "req-20260313-e2e",
            "source": "feishu",
            "source_user_id": "user-e2e",
            "entrypoint": "institutional_task",
            "title": "完成最小 sidecar 闭环",
            "message": "请从 ingress 一路跑到 reviewer approve。",
            "task_type_hint": "engineering",
        }
    )
    task_id = ingest_result["task_id"]

    result_adapter.apply_result(
        {
            "invoke_id": invoke.build_invoke(task_id, role="coordinator")["invoke_id"],
            "task_id": task_id,
            "role": "coordinator",
            "status": "succeeded",
            "output": {
                "goal": "跑通最小闭环",
                "acceptance_criteria": ["done"],
                "risk_notes": ["别绕过状态机"],
                "proposed_steps": ["coord", "exec", "review"],
            },
        }
    )
    result_adapter.apply_result(
        {
            "invoke_id": invoke.build_invoke(task_id, role="executor")["invoke_id"],
            "task_id": task_id,
            "role": "executor",
            "status": "succeeded",
            "output": {
                "result_summary": "闭环已跑通",
                "evidence": ["event-log", "state-machine"],
                "open_issues": [],
                "followup_notes": [],
            },
        }
    )
    result_adapter.apply_result(
        {
            "invoke_id": invoke.build_invoke(task_id, role="reviewer")["invoke_id"],
            "task_id": task_id,
            "role": "reviewer",
            "status": "succeeded",
            "output": {
                "review_decision": "approve",
                "review_comment": "闭环成立",
                "reasons": ["关键状态推进正确"],
                "required_rework": [],
                "residual_risk": "低",
            },
        }
    )

    task = get_task_by_id(app.conn, task_id)
    events = list_recent_events(app.conn, task_id, limit=20)

    assert task is not None
    assert task["state"] == "done"
    assert task["current_role"] is None
    assert task["review_decision"] == "approve"
    assert len(events) >= 6
