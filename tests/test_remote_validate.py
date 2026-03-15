from __future__ import annotations

from typing import Any

from sidecar.adapters.openclaw_runtime import OpenClawRequestError
from sidecar.remote_validate import run_remote_validation


class _ReachableGateway:
    def register_hooks(self, payload: dict[str, object]) -> dict[str, object]:
        return {"accepted": True, "ok": True, "status_code": 202, "response": payload}

    def probe_connectivity(self) -> dict[str, object]:
        return {"status": "reachable", "ok": True, "status_code": 200, "kind": None, "message": None}


class _ReachableRuntime:
    def probe_connectivity(self) -> dict[str, object]:
        return {"status": "reachable", "ok": True, "status_code": 204, "kind": None, "message": None}

    def submit_invoke(self, payload: dict[str, Any]) -> dict[str, object]:
        return {"accepted": True, "status_code": 202, "response": payload}


def test_run_remote_validation_reports_missing_remote_wiring() -> None:
    summary = run_remote_validation(config={"gateway_base_url": "", "runtime_invoke_url": "", "hooks_token": "", "public_base_url": ""})

    assert summary["ok"] is False
    assert "integration=local_only" in summary["blocking_issues"]
    assert summary["ops"]["ops"]["integration"]["status"] == "local_only"


def test_run_remote_validation_reports_runtime_invoke_ready_when_remote_wiring_is_complete() -> None:
    summary = run_remote_validation(
        config={
            "gateway_base_url": "",
            "runtime_invoke_url": "https://runtime.example.com/invoke",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com",
        },
        runtime_bridge=_ReachableRuntime(),
    )

    assert summary["ok"] is True
    assert summary["blocking_issues"] == []
    assert summary["ops"]["ops"]["integration"]["status"] == "runtime_invoke_ready"
    assert summary["ops"]["ops"]["integration"]["runtime_invoke"]["result_callback_ready"] is True


def test_run_remote_validation_can_dispatch_sample_task() -> None:
    summary = run_remote_validation(
        config={
            "gateway_base_url": "https://gateway.example.com",
            "runtime_invoke_url": "https://runtime.example.com/invoke",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com",
        },
        gateway_client=_ReachableGateway(),
        runtime_bridge=_ReachableRuntime(),
        dispatch_sample=True,
    )

    dispatch_sample = summary["dispatch_sample"]
    assert summary["ok"] is True
    assert dispatch_sample is not None
    assert dispatch_sample["dispatch_result"]["dispatched"] is True
    assert dispatch_sample["task"]["dispatch_status"] == "running"


class _FailedResultRuntime:
    def probe_connectivity(self) -> dict[str, object]:
        return {"status": "reachable", "ok": True, "status_code": 204, "kind": None, "message": None}

    def submit_invoke(self, payload: dict[str, Any]) -> dict[str, object]:
        return {
            "accepted": True,
            "status_code": 202,
            "response": {
                "result_status": "failed",
                "result_error_kind": "payload_error",
                "result_error_message": "JSON object not found",
            },
        }


def test_run_remote_validation_reports_failed_dispatch_sample_result() -> None:
    summary = run_remote_validation(
        config={
            "gateway_base_url": "",
            "runtime_invoke_url": "openclaw-cli://main",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com",
        },
        runtime_bridge=_FailedResultRuntime(),
        dispatch_sample=True,
    )

    assert summary["ok"] is False
    assert "dispatch_sample=result_failed:payload_error" in summary["blocking_issues"]


class _FailedCallbackRuntime:
    def probe_connectivity(self) -> dict[str, object]:
        return {"status": "reachable", "ok": True, "status_code": 204, "kind": None, "message": None}

    def submit_invoke(self, payload: dict[str, Any]) -> dict[str, object]:
        raise OpenClawRequestError(
            "OpenClaw CLI result callback rejected with HTTP 401: {\"code\":\"unauthorized\"}",
            kind="client_error",
            status_code=401,
            retryable=False,
            details={
                "stage": "callback",
                "callback_url": "http://sidecar.local/hooks/openclaw/result",
                "http_status": 401,
                "response_body_excerpt": '{"code":"unauthorized"}',
            },
        )


def test_run_remote_validation_reports_failed_dispatch_callback_stage() -> None:
    summary = run_remote_validation(
        config={
            "gateway_base_url": "",
            "runtime_invoke_url": "openclaw-cli://main",
            "hooks_token": "hook-secret",
            "public_base_url": "https://sidecar.example.com",
        },
        runtime_bridge=_FailedCallbackRuntime(),
        dispatch_sample=True,
    )

    assert summary["ok"] is False
    assert "dispatch_sample=submit_failed" in summary["blocking_issues"]
    assert "dispatch_sample=callback_failed:client_error" in summary["blocking_issues"]