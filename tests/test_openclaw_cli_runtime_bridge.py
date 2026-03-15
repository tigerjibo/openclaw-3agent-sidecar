from __future__ import annotations

import json
import io
import subprocess
from typing import Any
from urllib.error import HTTPError

import pytest

from sidecar.adapters.openclaw_runtime import CliOpenClawRuntimeBridge, OpenClawRequestError
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
    captured_command: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured_command["command"] = list(command)
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
    assert result["response"]["selected_agent_id"] == "main"
    assert result["response"]["cli_process"] == {
        "exit_code": 0,
        "stdout_excerpt": "plugin logs\n{\"runId\": \"run-001\", \"status\": \"ok\", \"summary\": \"completed\", \"result\": {\"payloads\": [{\"text\": \"{\\\"goal\\\": \\\"完成任务编排\\\", \\\"acceptance_criteria\\\": [\\\"任务进入 queued\\\"], \\\"risk_notes\\\": [\\\"避免状态漂移\\\"], \\\"proposed_steps\\\": [\\\"先分诊\\\", \\\"再执行\\\"]}\"}]}}",
        "stderr_excerpt": None,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }
    assert captured_command["command"][0:4] == ["openclaw", "agent", "--agent", "main"]
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
    assert result["response"]["cli_process"] == {
        "exit_code": 0,
        "stdout_excerpt": "{\"runId\": \"run-002\", \"status\": \"ok\", \"summary\": \"completed\", \"result\": {\"payloads\": [{\"text\": \"definitely not json\"}]}}",
        "stderr_excerpt": None,
        "stdout_truncated": False,
        "stderr_truncated": False,
    }
    assert result["response"]["result_error_kind"] == "payload_error"
    assert captured_request["body"]["status"] == "failed"
    assert captured_request["body"]["error_kind"] == "payload_error"
    assert "JSON object not found" in captured_request["body"]["error"]


def test_cli_runtime_bridge_surfaces_process_summary_when_agent_command_fails(monkeypatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            17,
            stdout="stdout line that should still be visible to operators",
            stderr="stderr line that explains why the CLI invocation failed",
        )

    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.subprocess.run", fake_run)

    bridge = CliOpenClawRuntimeBridge("main", openclaw_bin="openclaw")

    with pytest.raises(OpenClawRequestError) as exc_info:
        bridge.submit_invoke(
            {
                "invoke_id": "inv-003",
                "task_id": "task-003",
                "role": "coordinator",
                "trace_id": "trace-003",
                "goal": "验证失败时也返回进程摘要",
                "input": {"title": "失败路径", "message": "请故意返回错误。"},
                "constraints": {"structured_output_required": True},
                "callbacks": {
                    "result": {
                        "url": "http://sidecar.local/hooks/openclaw/result",
                        "headers": {"X-OpenClaw-Hooks-Token": "token-003"},
                    }
                },
            }
        )

    exc = exc_info.value
    assert exc.kind == "runtime_error"
    assert exc.status_code == 17
    assert exc.details == {
        "exit_code": 17,
        "stdout_excerpt": "stdout line that should still be visible to operators",
        "stderr_excerpt": "stderr line that explains why the CLI invocation failed",
        "stdout_truncated": False,
        "stderr_truncated": False,
    }


def test_cli_runtime_bridge_surfaces_callback_http_error_details(monkeypatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        payload = {
            "runId": "run-004",
            "status": "ok",
            "summary": "completed",
            "result": {"payloads": [{"text": json.dumps({"goal": "ok", "acceptance_criteria": [], "risk_notes": [], "proposed_steps": []}, ensure_ascii=False)}]},
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload, ensure_ascii=False), stderr="")

    def fake_urlopen(request, timeout: float = 0):
        raise HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            hdrs=None,
            fp=io.BytesIO(b'{"code":"unauthorized"}'),
        )

    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.subprocess.run", fake_run)
    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.urlopen", fake_urlopen)

    bridge = CliOpenClawRuntimeBridge("main", openclaw_bin="openclaw")

    with pytest.raises(OpenClawRequestError) as exc_info:
        bridge.submit_invoke(
            {
                "invoke_id": "inv-004",
                "task_id": "task-004",
                "role": "coordinator",
                "trace_id": "trace-004",
                "goal": "验证 callback 401",
                "input": {"title": "callback 错误", "message": "请返回 401。"},
                "constraints": {"structured_output_required": True},
                "callbacks": {
                    "result": {
                        "url": "http://sidecar.local/hooks/openclaw/result",
                        "headers": {"X-OpenClaw-Hooks-Token": "token-004"},
                    }
                },
            }
        )

    exc = exc_info.value
    assert exc.kind == "client_error"
    assert exc.status_code == 401
    assert exc.details == {
        "stage": "callback",
        "callback_url": "http://sidecar.local/hooks/openclaw/result",
        "http_status": 401,
        "response_body_excerpt": '{"code":"unauthorized"}',
    }


def test_cli_runtime_bridge_reports_callback_payload_error_for_non_json_response(monkeypatch) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        payload = {
            "runId": "run-005",
            "status": "ok",
            "summary": "completed",
            "result": {"payloads": [{"text": json.dumps({"goal": "ok", "acceptance_criteria": [], "risk_notes": [], "proposed_steps": []}, ensure_ascii=False)}]},
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload, ensure_ascii=False), stderr="")

    class _NonJsonResponse:
        status = 200

        def read(self) -> bytes:
            return b"definitely not json"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    def fake_urlopen(request, timeout: float = 0):
        return _NonJsonResponse()

    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.subprocess.run", fake_run)
    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.urlopen", fake_urlopen)

    bridge = CliOpenClawRuntimeBridge("main", openclaw_bin="openclaw")

    with pytest.raises(OpenClawRequestError) as exc_info:
        bridge.submit_invoke(
            {
                "invoke_id": "inv-005",
                "task_id": "task-005",
                "role": "coordinator",
                "trace_id": "trace-005",
                "goal": "验证 callback 非 JSON 返回体",
                "input": {"title": "callback payload error", "message": "请返回非 JSON。"},
                "constraints": {"structured_output_required": True},
                "callbacks": {
                    "result": {
                        "url": "http://sidecar.local/hooks/openclaw/result",
                        "headers": {"X-OpenClaw-Hooks-Token": "token-005"},
                    }
                },
            }
        )

    exc = exc_info.value
    assert exc.kind == "callback_payload_error"
    assert exc.status_code == 200
    assert exc.details == {
        "stage": "callback",
        "callback_url": "http://sidecar.local/hooks/openclaw/result",
        "http_status": 200,
        "response_body_excerpt": "definitely not json",
    }


def test_service_runner_builds_cli_runtime_bridge_from_scheme() -> None:
    runner = ServiceRunner(
        config={
            "db_path": ":memory:",
            "maintenance_interval_sec": 0,
            "runtime_invoke_url": "openclaw-cli://main",
            "runtime_cli_timeout_sec": 45.0,
            "public_base_url": "https://example.com/sidecar",
            "hooks_token": "token-003",
            "coordinator_agent_id": "coord-v2",
            "executor_agent_id": "exec-v2",
            "reviewer_agent_id": "review-v2",
        }
    )

    try:
        assert isinstance(runner._dispatcher.runtime_bridge, CliOpenClawRuntimeBridge)
        payload = runner.integration_payload()["runtime_invoke"]
        assert payload["invoke_url_configured"] is True
        assert payload["bridge"] == {
            "kind": "openclaw_cli",
            "agent_id": "main",
            "role_agent_mapping": {
                "configured_agents": {
                    "coordinator": "coord-v2",
                    "executor": "exec-v2",
                    "reviewer": "review-v2",
                },
                "fallback_agent_id": "main",
                "routing_mode": "role_specific",
            },
            "openclaw_bin": "openclaw",
            "timeout_sec": 45.0,
            "result_callback_url": "http://127.0.0.1:9600/hooks/openclaw/result",
        }
    finally:
        runner.stop()


def test_cli_runtime_bridge_uses_role_specific_agent_when_configured(monkeypatch) -> None:
    captured_command: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured_command["command"] = list(command)
        payload = {
            "runId": "run-006",
            "status": "ok",
            "summary": "completed",
            "result": {
                "payloads": [
                    {
                        "text": json.dumps(
                            {
                                "review_decision": "approve",
                                "review_comment": "looks good",
                                "reasons": ["all checks passed"],
                                "required_rework": [],
                                "residual_risk": "low",
                            },
                            ensure_ascii=False,
                        )
                    }
                ]
            },
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload, ensure_ascii=False), stderr="")

    def fake_urlopen(request, timeout: float = 0):
        return _FakeHttpResponse(201, {"ok": True})

    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.subprocess.run", fake_run)
    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.urlopen", fake_urlopen)

    bridge = CliOpenClawRuntimeBridge(
        "main",
        openclaw_bin="openclaw",
        role_agent_ids={"reviewer": "review-v2"},
    )
    result = bridge.submit_invoke(
        {
            "invoke_id": "inv-006",
            "task_id": "task-006",
            "role": "reviewer",
            "trace_id": "trace-006",
            "goal": "验证 reviewer 走独立 agent",
            "input": {"title": "role specific reviewer", "message": "请审查。"},
            "constraints": {"structured_output_required": True},
            "callbacks": {
                "result": {
                    "url": "http://sidecar.local/hooks/openclaw/result",
                    "headers": {"X-OpenClaw-Hooks-Token": "token-006"},
                }
            },
        }
    )

    assert captured_command["command"][0:4] == ["openclaw", "agent", "--agent", "review-v2"]
    assert result["response"]["selected_agent_id"] == "review-v2"


def test_cli_runtime_bridge_falls_back_to_default_agent_when_role_mapping_missing(monkeypatch) -> None:
    captured_command: dict[str, Any] = {}

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured_command["command"] = list(command)
        payload = {
            "runId": "run-007",
            "status": "ok",
            "summary": "completed",
            "result": {
                "payloads": [
                    {
                        "text": json.dumps(
                            {
                                "result_summary": "done",
                                "evidence": ["e1"],
                                "open_issues": [],
                                "followup_notes": [],
                            },
                            ensure_ascii=False,
                        )
                    }
                ]
            },
        }
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(payload, ensure_ascii=False), stderr="")

    def fake_urlopen(request, timeout: float = 0):
        return _FakeHttpResponse(201, {"ok": True})

    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.subprocess.run", fake_run)
    monkeypatch.setattr("sidecar.adapters.openclaw_runtime.urlopen", fake_urlopen)

    bridge = CliOpenClawRuntimeBridge(
        "main",
        openclaw_bin="openclaw",
        role_agent_ids={"coordinator": "coord-v2"},
    )
    result = bridge.submit_invoke(
        {
            "invoke_id": "inv-007",
            "task_id": "task-007",
            "role": "executor",
            "trace_id": "trace-007",
            "goal": "验证缺失映射时回退 main",
            "input": {"title": "role fallback executor", "message": "请执行。"},
            "constraints": {"structured_output_required": True},
            "callbacks": {
                "result": {
                    "url": "http://sidecar.local/hooks/openclaw/result",
                    "headers": {"X-OpenClaw-Hooks-Token": "token-007"},
                }
            },
        }
    )

    assert captured_command["command"][0:4] == ["openclaw", "agent", "--agent", "main"]
    assert result["response"]["selected_agent_id"] == "main"
