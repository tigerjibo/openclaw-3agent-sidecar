from __future__ import annotations

import json
import subprocess
from typing import Any

from sidecar.adapters.openclaw_runtime import CliOpenClawRuntimeBridge
from sidecar.service_runner import ServiceRunner


class _FakeHttpResponse:
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_cli_runtime_bridge_posts_structured_result_callback(monkeypatch) -> None:
    captured_request: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        payload = {
            "runId": "run-001",
            "status": "ok",
            "summary": "completed",
            "result": {
                "payloads": [
                    {
                        "text": json.dumps(
                            {
                                "goal": "完成任务编排",
                                "acceptance_criteria": ["任务进入 queued"],
                                "risk_notes": ["避免状态漂移"],
                                "proposed_steps": ["先分诊", "再执行"],
                            },
                            ensure_ascii=False,
                        )
                    }
                ]
            },
        }
        return subprocess.CompletedProcess(command, 0, stdout="plugin logs\n" + json.dumps(payload, ensure_ascii=False), stderr="")

    def fake_urlopen(request, timeout: float = 0):
        captured_request["url"] = request.full_url
        captured_request["headers"] = dict(request.header_items())
        captured_request["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHttpResponse(201, {"ok": True})

    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.subprocess.run", fake_run)
    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.urlopen", fake_urlopen)

    bridge = CliOpenClawRuntimeBridge("main", openclaw_bin="openclaw")
    result = bridge.submit_invoke(
        {
            "invoke_id": "inv-001",
            "task_id": "task-001",
            "role": "coordinator",
            "trace_id": "trace-001",
            "goal": "归纳任务目标并形成 brief",
            "input": {"title": "实现最小闭环", "message": "请先做任务拆解。"},
            "constraints": {"structured_output_required": True},
            "callbacks": {
                "result": {
                    "url": "http://sidecar.local/hooks/openclaw/result",
                    "headers": {"X-OpenClaw-Hooks-Token": "token-001"},
                }
            },
        }
    )

    assert result["accepted"] is True
    assert result["submission_id"] == "run-001"
    assert captured_request["url"] == "http://sidecar.local/hooks/openclaw/result"
    normalized_headers = {str(key).lower(): value for key, value in captured_request["headers"].items()}
    assert normalized_headers["x-openclaw-hooks-token"] == "token-001"
    assert captured_request["body"]["status"] == "succeeded"
    assert captured_request["body"]["output"]["goal"] == "完成任务编排"
    assert captured_request["body"]["output"]["acceptance_criteria"] == ["任务进入 queued"]


def test_cli_runtime_bridge_reports_failed_result_when_agent_output_is_not_json(monkeypatch) -> None:
    captured_request: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        payload = {
            "runId": "run-002",
            "status": "ok",
            "summary": "completed",
            "result": {"payloads": [{"text": "definitely not json"}]},
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload, ensure_ascii=False), stderr="")

    def fake_urlopen(request, timeout: float = 0):
        captured_request["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeHttpResponse(201, {"ok": True})

    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.subprocess.run", fake_run)
    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.urlopen", fake_urlopen)

    bridge = CliOpenClawRuntimeBridge("main", openclaw_bin="openclaw")
    result = bridge.submit_invoke(
        {
            "invoke_id": "inv-002",
            "task_id": "task-002",
            "role": "executor",
            "trace_id": "trace-002",
            "goal": "执行任务并提交证据与结果摘要",
            "input": {"title": "实现最小闭环", "message": "请执行并给出结论。"},
            "constraints": {"structured_output_required": True},
            "callbacks": {
                "result": {
                    "url": "http://sidecar.local/hooks/openclaw/result",
                    "headers": {"X-OpenClaw-Hooks-Token": "token-002"},
                }
            },
        }
    )

    assert result["accepted"] is True
    assert result["response"]["result_error_kind"] == "payload_error"
    assert captured_request["body"]["status"] == "failed"
    assert captured_request["body"]["error_kind"] == "payload_error"
    assert "JSON object not found" in captured_request["body"]["error"]


def test_service_runner_builds_cli_runtime_bridge_from_scheme() -> None:
    runner = ServiceRunner(
        config={
            "db_path": ":memory:",
            "maintenance_interval_sec": 0,
            "runtime_invoke_url": "openclaw-cli://main",
            "public_base_url": "https://example.com/sidecar",
            "hooks_token": "token-003",
        }
    )

    try:
        assert isinstance(runner._dispatcher.runtime_bridge, CliOpenClawRuntimeBridge)
        payload = runner.integration_payload()["runtime_invoke"]
        assert payload["invoke_url_configured"] is True
        assert payload["bridge"] == {
            "kind": "openclaw_cli",
            "agent_id": "main",
            "openclaw_bin": "openclaw",
            "timeout_sec": 120.0,
            "result_callback_url": "http://127.0.0.1:9600/hooks/openclaw/result",
        }
    finally:
        runner.stop()
