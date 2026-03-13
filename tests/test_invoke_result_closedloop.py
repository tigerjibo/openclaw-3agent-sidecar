"""Task 7: Dispatch failure resilience and duplicate result tests."""
from __future__ import annotations

from sidecar.adapters.agent_invoke import AgentInvokeAdapter
from sidecar.adapters.ingress import IngressAdapter
from sidecar.adapters.result import ResultAdapter
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


def _ingest(app: TaskKernelApiApp, request_id: str) -> str:
    ingress = IngressAdapter(app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-closedloop",
            "entrypoint": "institutional_task",
            "title": "closedloop test",
            "message": "Closed loop test.",
            "task_type_hint": "engineering",
        }
    )["task_id"]


class FailingBridge:
    def submit_invoke(self, payload):
        raise RuntimeError("upstream unreachable")


# ---------- Dispatch failure resilience ----------

def test_dispatch_records_submission_error_but_still_marks_running() -> None:
    """If runtime submission fails, dispatcher should still mark task as
    running (so recovery can handle it) and include the error in the result."""
    app = _build_app()
    task_id = _ingest(app, "req-dispatch-fail")
    dispatcher = TaskDispatcher(app, runtime_bridge=FailingBridge())

    result = dispatcher.dispatch_task(task_id)

    assert result["dispatched"] is True
    assert result["submission_error"] is not None
    assert "unreachable" in result["submission_error"]

    task = get_task_by_id(app.conn, task_id)
    assert task["dispatch_status"] == "running"


# ---------- Duplicate result (idempotency) ----------

def test_duplicate_result_is_idempotent() -> None:
    """Sending the same invoke_id twice should return the current task state
    without error and without advancing the state machine again."""
    app = _build_app()
    task_id = _ingest(app, "req-dup-result")
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)

    invoke_id = invoke.build_invoke(task_id, role="coordinator")["invoke_id"]
    first = result_adapter.apply_result(
        {
            "invoke_id": invoke_id,
            "task_id": task_id,
            "role": "coordinator",
            "status": "succeeded",
            "output": {
                "goal": "dup test",
                "acceptance_criteria": ["done"],
                "risk_notes": [],
                "proposed_steps": [],
            },
        }
    )
    assert first["state"] == "queued"

    # Send same invoke_id again
    second = result_adapter.apply_result(
        {
            "invoke_id": invoke_id,
            "task_id": task_id,
            "role": "coordinator",
            "status": "succeeded",
            "output": {},
        }
    )
    # Should return the same state, not advance further
    assert second["state"] == first["state"]
    assert second["version"] == first["version"]


# ---------- Full cycle with dispatcher ----------

def test_full_cycle_with_dispatcher_coordination() -> None:
    """Full coordinator → executor → reviewer cycle using dispatcher for dispatch."""
    app = _build_app()
    task_id = _ingest(app, "req-full-cycle")
    dispatcher = TaskDispatcher(app)
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)

    # Dispatch coordinator
    d1 = dispatcher.dispatch_task(task_id)
    assert d1["dispatched"]
    assert d1["invoke_payload"]["role"] == "coordinator"

    # Coordinator result
    result_adapter.apply_result(
        {
            "invoke_id": d1["invoke_payload"]["invoke_id"],
            "task_id": task_id,
            "role": "coordinator",
            "status": "succeeded",
            "output": {
                "goal": "full cycle",
                "acceptance_criteria": ["verified"],
                "risk_notes": [],
                "proposed_steps": ["exec", "review"],
            },
        }
    )
    task = get_task_by_id(app.conn, task_id)
    assert task["state"] == "queued"
    assert task["dispatch_status"] == "idle"

    # Dispatch executor
    d2 = dispatcher.dispatch_task(task_id)
    assert d2["dispatched"]
    assert d2["invoke_payload"]["role"] == "executor"

    # Executor result
    result_adapter.apply_result(
        {
            "invoke_id": d2["invoke_payload"]["invoke_id"],
            "task_id": task_id,
            "role": "executor",
            "status": "succeeded",
            "output": {
                "result_summary": "done",
                "evidence": ["test passed"],
                "open_issues": [],
                "followup_notes": [],
            },
        }
    )
    task = get_task_by_id(app.conn, task_id)
    assert task["state"] == "reviewing"
    assert task["dispatch_status"] == "idle"

    # Dispatch reviewer
    d3 = dispatcher.dispatch_task(task_id)
    assert d3["dispatched"]
    assert d3["invoke_payload"]["role"] == "reviewer"

    # Reviewer approves
    result_adapter.apply_result(
        {
            "invoke_id": d3["invoke_payload"]["invoke_id"],
            "task_id": task_id,
            "role": "reviewer",
            "status": "succeeded",
            "output": {
                "review_decision": "approve",
                "review_comment": "LGTM",
                "reasons": ["all good"],
                "required_rework": [],
                "residual_risk": "none",
            },
        }
    )
    task = get_task_by_id(app.conn, task_id)
    assert task["state"] == "done"
    assert task["dispatch_status"] == "idle"
