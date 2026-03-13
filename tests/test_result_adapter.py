from sidecar.adapters.agent_invoke import AgentInvokeAdapter
from sidecar.adapters.ingress import IngressAdapter
from sidecar.adapters.result import ResultAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.models import get_task_by_id
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def _create_task(app: TaskKernelApiApp) -> str:
    ingress = IngressAdapter(app)
    result = ingress.ingest(
        {
            "request_id": "req-20260313-003",
            "source": "feishu",
            "source_user_id": "user-review",
            "entrypoint": "institutional_task",
            "title": "实现任务编排",
            "message": "实现一个最小 sidecar 任务编排系统。",
            "task_type_hint": "engineering",
        }
    )
    return result["task_id"]


def test_result_adapter_applies_coordinator_and_executor_success() -> None:
    app = _build_app()
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)
    task_id = _create_task(app)

    coordinator_invoke = invoke.build_invoke(task_id, role="coordinator")
    result_adapter.apply_result(
        {
            "invoke_id": coordinator_invoke["invoke_id"],
            "task_id": task_id,
            "role": "coordinator",
            "trace_id": coordinator_invoke["trace_id"],
            "status": "succeeded",
            "output": {
                "goal": "完成 sidecar 任务编排",
                "acceptance_criteria": ["能创建任务", "能推进状态"],
                "risk_notes": ["避免绕过状态机"],
                "proposed_steps": ["先建 ingress", "再接 result"],
            },
        }
    )

    after_coord = get_task_by_id(app.conn, task_id)
    assert after_coord is not None
    assert after_coord["state"] == "queued"
    assert after_coord["current_role"] == "executor"
    assert after_coord["goal"] == "完成 sidecar 任务编排"

    executor_invoke = invoke.build_invoke(task_id, role="executor")
    result_adapter.apply_result(
        {
            "invoke_id": executor_invoke["invoke_id"],
            "task_id": task_id,
            "role": "executor",
            "trace_id": executor_invoke["trace_id"],
            "status": "succeeded",
            "output": {
                "result_summary": "已完成 ingress/result 最小闭环",
                "evidence": ["tests passing", "compileall ok"],
                "open_issues": ["scheduler 未实现"],
                "followup_notes": ["后续补 dispatcher"],
            },
        }
    )

    after_exec = get_task_by_id(app.conn, task_id)
    assert after_exec is not None
    assert after_exec["state"] == "reviewing"
    assert after_exec["current_role"] == "reviewer"
    assert after_exec["result_summary"] == "已完成 ingress/result 最小闭环"


def test_result_adapter_handles_reviewer_reject_and_approve() -> None:
    app = _build_app()
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)
    task_id = _create_task(app)

    coordinator_invoke = invoke.build_invoke(task_id, role="coordinator")
    result_adapter.apply_result(
        {
            "invoke_id": coordinator_invoke["invoke_id"],
            "task_id": task_id,
            "role": "coordinator",
            "trace_id": coordinator_invoke["trace_id"],
            "status": "succeeded",
            "output": {
                "goal": "完成评审闭环",
                "acceptance_criteria": ["review 可 reject/approve"],
                "risk_notes": [],
                "proposed_steps": ["执行", "评审"],
            },
        }
    )
    executor_invoke = invoke.build_invoke(task_id, role="executor")
    result_adapter.apply_result(
        {
            "invoke_id": executor_invoke["invoke_id"],
            "task_id": task_id,
            "role": "executor",
            "trace_id": executor_invoke["trace_id"],
            "status": "succeeded",
            "output": {
                "result_summary": "执行完成",
                "evidence": ["artifact-a"],
                "open_issues": [],
                "followup_notes": [],
            },
        }
    )

    reject_invoke = invoke.build_invoke(task_id, role="reviewer")
    result_adapter.apply_result(
        {
            "invoke_id": reject_invoke["invoke_id"],
            "task_id": task_id,
            "role": "reviewer",
            "trace_id": reject_invoke["trace_id"],
            "status": "succeeded",
            "output": {
                "review_decision": "reject",
                "review_comment": "还缺少恢复策略",
                "reasons": ["缺 recovery"],
                "required_rework": ["补 recovery 设计"],
                "residual_risk": "重启后可能悬挂",
            },
        }
    )

    rejected = get_task_by_id(app.conn, task_id)
    assert rejected is not None
    assert rejected["state"] == "rework"
    assert rejected["current_role"] == "executor"
    assert rejected["review_decision"] == "reject"
    assert rejected["review_comment"] == "还缺少恢复策略"

    rework_invoke = invoke.build_invoke(task_id, role="executor")
    result_adapter.apply_result(
        {
            "invoke_id": rework_invoke["invoke_id"],
            "task_id": task_id,
            "role": "executor",
            "trace_id": rework_invoke["trace_id"],
            "status": "succeeded",
            "output": {
                "result_summary": "已补 recovery 设计",
                "evidence": ["artifact-b"],
                "open_issues": [],
                "followup_notes": [],
            },
        }
    )
    approve_invoke = invoke.build_invoke(task_id, role="reviewer")
    result_adapter.apply_result(
        {
            "invoke_id": approve_invoke["invoke_id"],
            "task_id": task_id,
            "role": "reviewer",
            "trace_id": approve_invoke["trace_id"],
            "status": "succeeded",
            "output": {
                "review_decision": "approve",
                "review_comment": "可以通过",
                "reasons": ["关键缺口已关闭"],
                "required_rework": [],
                "residual_risk": "低",
            },
        }
    )

    approved = get_task_by_id(app.conn, task_id)
    assert approved is not None
    assert approved["state"] == "done"
    assert approved["review_decision"] == "approve"
