from __future__ import annotations

from sidecar.adapters.ingress import IngressAdapter
from sidecar.adapters.openclaw_runtime import OpenClawRequestError
from sidecar.adapters.result import ResultAdapter
from sidecar.api import TaskKernelApiApp
from sidecar.models import get_task_by_id
from sidecar.runtime.dispatcher import TaskDispatcher
from sidecar.runtime.recovery import TaskRecovery
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


class RetryableFailBridge:
    def submit_invoke(self, payload):
        raise OpenClawRequestError(
            "gateway timeout",
            kind="timeout",
            retryable=True,
            status_code=None,
        )


class PermanentFailBridge:
    def submit_invoke(self, payload):
        raise OpenClawRequestError(
            "bad request",
            kind="client_error",
            retryable=False,
            status_code=400,
        )


class ConfigurationFailBridge:
    def submit_invoke(self, payload):
        raise OpenClawRequestError(
            "OpenClaw CLI not found",
            kind="configuration_error",
            retryable=False,
            status_code=None,
        )


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
            "source_user_id": "user-dispatch-retry",
            "entrypoint": "institutional_task",
            "title": "dispatch retry strategy",
            "message": "retry strategy test",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_retryable_submit_failure_can_be_released_by_recovery() -> None:
    app = _build_app()
    task_id = _ingest(app, "req-retryable-submit")
    dispatcher = TaskDispatcher(app, runtime_bridge=RetryableFailBridge())
    recovery = TaskRecovery(app)

    result = dispatcher.dispatch_task(task_id)
    assert result["dispatched"] is False
    assert result["submission_retryable"] is True
    assert result["submission_error_kind"] == "timeout"
    assert result["submission_recovery_action"] == "retry"

    task = get_task_by_id(app.conn, task_id)
    assert task["dispatch_status"] == "submit_failed"
    assert task["dispatch_error_retryable"] == 1

    recovered = recovery.recover_retryable_submit_failures()
    assert recovered == [task_id]

    task = get_task_by_id(app.conn, task_id)
    assert task["dispatch_status"] == "idle"


def test_non_retryable_submit_failure_is_not_released_by_recovery() -> None:
    app = _build_app()
    task_id = _ingest(app, "req-permanent-submit")
    dispatcher = TaskDispatcher(app, runtime_bridge=PermanentFailBridge())
    recovery = TaskRecovery(app)

    result = dispatcher.dispatch_task(task_id)
    assert result["dispatched"] is False
    assert result["submission_retryable"] is False
    assert result["submission_error_kind"] == "client_error"
    assert result["submission_status_code"] == 400
    assert result["submission_recovery_action"] == "hold"

    recovered = recovery.recover_retryable_submit_failures()
    assert recovered == []

    task = get_task_by_id(app.conn, task_id)
    assert task["dispatch_status"] == "submit_failed"
    assert task["dispatch_error_retryable"] == 0


def test_configuration_error_blocks_task_instead_of_leaving_retry_loop() -> None:
    app = _build_app()
    task_id = _ingest(app, "req-configuration-submit")
    dispatcher = TaskDispatcher(app, runtime_bridge=ConfigurationFailBridge())
    recovery = TaskRecovery(app)

    result = dispatcher.dispatch_task(task_id)

    assert result["dispatched"] is False
    assert result["submission_error_kind"] == "configuration_error"
    assert result["submission_recovery_action"] == "block"

    recovered = recovery.recover_retryable_submit_failures()
    assert recovered == []

    task = get_task_by_id(app.conn, task_id)
    assert task["dispatch_status"] == "idle"
    assert task["blocked"] == 1
    assert task["waiting_on"] == "runtime_configuration"
    assert "manual repair" in str(task["block_reason"])
    assert task["dispatch_error_retryable"] == 0


def test_late_failure_ignored_does_not_reblock_already_progressed_task() -> None:
    class LateFailBridge:
        def __init__(self, app: TaskKernelApiApp) -> None:
            self.result_adapter = ResultAdapter(app)

        def submit_invoke(self, payload):
            self.result_adapter.apply_result(
                {
                    "invoke_id": payload["invoke_id"],
                    "task_id": payload["task_id"],
                    "role": payload["role"],
                    "trace_id": payload["trace_id"],
                    "status": "succeeded",
                    "output": {
                        "goal": "progressed before failure surfaced",
                        "acceptance_criteria": ["queued"],
                        "risk_notes": [],
                        "proposed_steps": [],
                    },
                }
            )
            raise OpenClawRequestError(
                "gateway 504 after callback completed",
                kind="server_error",
                retryable=True,
                status_code=504,
            )

    app = _build_app()
    task_id = _ingest(app, "req-late-failure-ignored")
    dispatcher = TaskDispatcher(app, runtime_bridge=LateFailBridge(app))

    result = dispatcher.dispatch_task(task_id)

    assert result["dispatched"] is True
    assert result["submission_state"] == "late_failure_ignored"
    assert result["submission_recovery_action"] == "ignored"

    task = get_task_by_id(app.conn, task_id)
    assert task["state"] == "queued"
    assert task["current_role"] == "executor"
    assert task["dispatch_status"] == "idle"
    assert task["blocked"] == 0
