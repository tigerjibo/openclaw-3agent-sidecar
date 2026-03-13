"""Task 8: Version optimistic lock coverage verification.

Verifies that:
1. Success paths check expected_version (already covered in existing tests)
2. Block path does NOT check version (documented as intentional — blocking
   is a flag operation that doesn't advance the state machine)
3. Duplicate result replay via idempotency_key works across all paths
4. Concurrent duplicate result is rejected by idempotency, not by version
"""
from __future__ import annotations

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


def _ingest(app: TaskKernelApiApp, request_id: str) -> str:
    ingress = IngressAdapter(app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-version",
            "entrypoint": "institutional_task",
            "title": "version check task",
            "message": "Version coverage verification.",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_success_path_increments_version() -> None:
    """Each successful state transition should increment the version."""
    app = _build_app()
    task_id = _ingest(app, "req-ver-success")
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)

    task_before = get_task_by_id(app.conn, task_id)
    v0 = task_before["version"]

    result_adapter.apply_result(
        {
            "invoke_id": invoke.build_invoke(task_id, role="coordinator")["invoke_id"],
            "task_id": task_id,
            "role": "coordinator",
            "status": "succeeded",
            "output": {
                "goal": "v check",
                "acceptance_criteria": [],
                "risk_notes": [],
                "proposed_steps": [],
            },
        }
    )

    task_after = get_task_by_id(app.conn, task_id)
    assert task_after["version"] > v0
    assert task_after["state"] == "queued"


def test_block_path_increments_version() -> None:
    """Blocking a task should still increment the version (via api._block_task)."""
    app = _build_app()
    task_id = _ingest(app, "req-ver-block")
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)

    task_before = get_task_by_id(app.conn, task_id)
    v0 = task_before["version"]

    result_adapter.apply_result(
        {
            "invoke_id": invoke.build_invoke(task_id, role="coordinator")["invoke_id"],
            "task_id": task_id,
            "role": "coordinator",
            "status": "blocked",
            "output": {"blocked_reason": "missing info"},
        }
    )

    task_after = get_task_by_id(app.conn, task_id)
    # Block should increment version (the explicit UPDATE in _block_task does version + 1)
    assert task_after["version"] > v0
    assert task_after["blocked"] == 1


def test_failed_path_increments_version() -> None:
    """A failed result that triggers blocking should also increment version."""
    app = _build_app()
    task_id = _ingest(app, "req-ver-failed")
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)

    task_before = get_task_by_id(app.conn, task_id)
    v0 = task_before["version"]

    result_adapter.apply_result(
        {
            "invoke_id": invoke.build_invoke(task_id, role="coordinator")["invoke_id"],
            "task_id": task_id,
            "role": "coordinator",
            "status": "failed",
            "error": "coordinator crashed",
        }
    )

    task_after = get_task_by_id(app.conn, task_id)
    assert task_after["version"] > v0
    assert task_after["blocked"] == 1


def test_concurrent_duplicate_result_rejected_by_idempotency() -> None:
    """Sending the exact same invoke_id twice should be idempotent.
    The second call returns the current task state without any changes."""
    app = _build_app()
    task_id = _ingest(app, "req-ver-dup")
    invoke = AgentInvokeAdapter(app)
    result_adapter = ResultAdapter(app)

    invoke_id = invoke.build_invoke(task_id, role="coordinator")["invoke_id"]
    payload = {
        "invoke_id": invoke_id,
        "task_id": task_id,
        "role": "coordinator",
        "status": "succeeded",
        "output": {
            "goal": "dup",
            "acceptance_criteria": [],
            "risk_notes": [],
            "proposed_steps": [],
        },
    }

    first = result_adapter.apply_result(payload)
    first_version = first["version"]

    second = result_adapter.apply_result(payload)
    # Idempotent replay: same version, same state
    assert second["version"] == first_version
    assert second["state"] == first["state"]


def test_stale_version_rejected_in_transition() -> None:
    """Direct API call with stale expected_version should be rejected."""
    app = _build_app()
    task_id = _ingest(app, "req-ver-stale")

    task = get_task_by_id(app.conn, task_id)
    stale_version = task["version"]

    # First transition succeeds
    resp1 = app.handle_request("POST", f"/tasks/{task_id}/transition", body={
        "actor_role": "coordinator",
        "new_state": "triaging",
        "expected_version": stale_version,
    })
    assert resp1["status"] == 200

    # Same stale version should now be rejected
    resp2 = app.handle_request("POST", f"/tasks/{task_id}/transition", body={
        "actor_role": "coordinator",
        "new_state": "queued",
        "expected_version": stale_version,
    })
    assert resp2["status"] == 409
    assert resp2["body"]["code"] == "conflict"
