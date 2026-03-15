from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenClawRequestError(RuntimeError):
    """Structured error from OpenClaw HTTP requests."""

    def __init__(self, message: str, *, kind: str, status_code: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retryable = retryable


class OpenClawRuntimeBridge(Protocol):
    def submit_invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


class CliOpenClawRuntimeBridge:
    def __init__(
        self,
        agent_id: str,
        *,
        openclaw_bin: str | None = None,
        result_callback_url: str = "",
        hooks_token: str = "",
        timeout_sec: float = 120.0,
    ) -> None:
        normalized_agent_id = str(agent_id).strip()
        if not normalized_agent_id:
            raise ValueError("agent_id is required")
        self.agent_id = normalized_agent_id
        self.timeout_sec = float(timeout_sec)
        self.openclaw_bin = self._resolve_openclaw_bin(openclaw_bin)
        self.result_callback_url = str(result_callback_url).strip()
        self.hooks_token = str(hooks_token).strip()

    def submit_invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = self._build_request_payload(payload)
        callback = dict((request_payload.get("callbacks") or {}).get("result") or {})
        callback_url = str(callback.get("url") or "").strip()
        if not callback_url:
            raise OpenClawRequestError(
                "OpenClaw CLI bridge requires callbacks.result.url",
                kind="configuration_error",
                retryable=False,
            )

        role = str(request_payload.get("role") or "").strip()
        invoke_id = str(request_payload.get("invoke_id") or "").strip()
        task_id = str(request_payload.get("task_id") or "").strip()
        trace_id = str(request_payload.get("trace_id") or "").strip()
        if not role or not invoke_id or not task_id or not trace_id:
            raise OpenClawRequestError(
                "invoke payload is missing required identifiers",
                kind="payload_error",
                retryable=False,
            )

        cli_payload = self._run_agent_command(self._build_agent_message(request_payload))
        result_payload = {
            "invoke_id": invoke_id,
            "task_id": task_id,
            "role": role,
            "trace_id": trace_id,
        }

        try:
            assistant_text = self._extract_assistant_text(cli_payload)
            result_payload["status"] = "succeeded"
            result_payload["output"] = self._parse_role_output(role, assistant_text)
        except Exception as exc:
            result_payload["status"] = "failed"
            result_payload["error"] = str(exc)

        callback_response = self._post_callback_result(callback_url, callback, result_payload)
        return {
            "accepted": True,
            "status_code": int(callback_response.get("status_code") or 200),
            "submission_id": cli_payload.get("runId"),
            "response": {
                "cli": cli_payload,
                "callback": callback_response,
                "result_status": result_payload["status"],
            },
        }

    def probe_connectivity(self) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                [self.openclaw_bin, "help", "agent"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=min(self.timeout_sec, 15.0),
                check=False,
            )
        except FileNotFoundError:
            return {
                "status": "unreachable",
                "ok": False,
                "status_code": None,
                "kind": "probe_error",
                "message": f"OpenClaw CLI not found: {self.openclaw_bin}",
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "unreachable",
                "ok": False,
                "status_code": None,
                "kind": "timeout",
                "message": "Timed out probing OpenClaw CLI.",
            }

        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip()
            return {
                "status": "unreachable",
                "ok": False,
                "status_code": completed.returncode,
                "kind": "probe_error",
                "message": details or "OpenClaw CLI help command failed.",
            }

        return {
            "status": "reachable",
            "ok": True,
            "status_code": 0,
            "kind": None,
            "message": None,
        }

    def _run_agent_command(self, message: str) -> dict[str, Any]:
        command = [
            self.openclaw_bin,
            "agent",
            "--agent",
            self.agent_id,
            "--message",
            message,
            "--json",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.timeout_sec,
                check=False,
            )
        except FileNotFoundError as exc:
            raise OpenClawRequestError(
                f"OpenClaw CLI not found: {self.openclaw_bin}",
                kind="configuration_error",
                retryable=False,
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise OpenClawRequestError(
                f"Timeout waiting for OpenClaw CLI after {self.timeout_sec}s",
                kind="timeout",
                retryable=True,
            ) from exc

        raw = (completed.stdout or "").strip()
        if completed.returncode != 0:
            details = (completed.stderr or raw or "").strip()
            raise OpenClawRequestError(
                f"OpenClaw CLI agent command failed: {details}",
                kind="runtime_error",
                status_code=completed.returncode,
                retryable=False,
            )

        try:
            payload = self._extract_json_document(raw)
        except ValueError as exc:
            raise OpenClawRequestError(
                f"OpenClaw CLI returned non-JSON output: {raw[:400]}",
                kind="payload_error",
                retryable=False,
            ) from exc

        if str(payload.get("status") or "").strip() != "ok":
            raise OpenClawRequestError(
                f"OpenClaw CLI returned non-ok status: {payload}",
                kind="runtime_error",
                retryable=False,
            )
        return payload

    def _build_request_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = dict(payload)
        result_callback = self._build_result_callback_payload()
        if result_callback is None:
            return request_payload

        callbacks = dict(request_payload.get("callbacks") or {})
        callbacks["result"] = result_callback
        request_payload["callbacks"] = callbacks
        return request_payload

    def _build_result_callback_payload(self) -> dict[str, Any] | None:
        if not self.result_callback_url:
            return None

        payload: dict[str, Any] = {"url": self.result_callback_url}
        if self.hooks_token:
            payload["headers"] = {"X-OpenClaw-Hooks-Token": self.hooks_token}
        return payload

    def _build_agent_message(self, payload: dict[str, Any]) -> str:
        role = str(payload.get("role") or "").strip()
        schema = self._role_output_schema(role)
        task_packet = {
            "invoke_id": payload.get("invoke_id"),
            "task_id": payload.get("task_id"),
            "role": role,
            "trace_id": payload.get("trace_id"),
            "goal": payload.get("goal"),
            "input": payload.get("input") or {},
            "constraints": payload.get("constraints") or {},
        }
        return "\n".join(
            [
                "You are handling one sidecar role turn for OpenClaw.",
                f"Role: {role}",
                "Return exactly one JSON object and nothing else.",
                "Do not use markdown fences.",
                "Required JSON schema:",
                json.dumps(schema, ensure_ascii=False, indent=2),
                "Task packet:",
                json.dumps(task_packet, ensure_ascii=False, indent=2),
            ]
        )

    def _role_output_schema(self, role: str) -> dict[str, Any]:
        if role == "coordinator":
            return {
                "goal": "string",
                "acceptance_criteria": ["string"],
                "risk_notes": ["string"],
                "proposed_steps": ["string"],
            }
        if role == "executor":
            return {
                "result_summary": "string",
                "evidence": ["string"],
                "open_issues": ["string"],
                "followup_notes": ["string"],
            }
        if role == "reviewer":
            return {
                "review_decision": "approve|reject",
                "review_comment": "string",
                "reasons": ["string"],
                "required_rework": ["string"],
                "residual_risk": "string",
            }
        raise ValueError(f"unsupported role: {role}")

    def _extract_assistant_text(self, cli_payload: dict[str, Any]) -> str:
        result = dict(cli_payload.get("result") or {})
        payloads = result.get("payloads") or []
        texts = [str(item.get("text") or "").strip() for item in payloads if str(item.get("text") or "").strip()]
        if not texts:
            raise ValueError("OpenClaw CLI result did not include any text payload")
        return "\n".join(texts)

    def _parse_role_output(self, role: str, text: str) -> dict[str, Any]:
        parsed = self._extract_json_document(text)
        if role == "coordinator":
            return {
                "goal": str(parsed.get("goal") or "").strip(),
                "acceptance_criteria": self._normalize_string_list(parsed.get("acceptance_criteria")),
                "risk_notes": self._normalize_string_list(parsed.get("risk_notes")),
                "proposed_steps": self._normalize_string_list(parsed.get("proposed_steps")),
            }
        if role == "executor":
            return {
                "result_summary": str(parsed.get("result_summary") or "").strip(),
                "evidence": self._normalize_string_list(parsed.get("evidence")),
                "open_issues": self._normalize_string_list(parsed.get("open_issues")),
                "followup_notes": self._normalize_string_list(parsed.get("followup_notes")),
            }
        if role == "reviewer":
            decision = str(parsed.get("review_decision") or "").strip().lower()
            if decision not in {"approve", "reject"}:
                raise ValueError(f"unsupported review_decision: {decision or '<empty>'}")
            return {
                "review_decision": decision,
                "review_comment": str(parsed.get("review_comment") or "").strip(),
                "reasons": self._normalize_string_list(parsed.get("reasons")),
                "required_rework": self._normalize_string_list(parsed.get("required_rework")),
                "residual_risk": str(parsed.get("residual_risk") or "").strip(),
            }
        raise ValueError(f"unsupported role: {role}")

    def _post_callback_result(self, callback_url: str, callback: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            callback_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._callback_headers(callback),
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read()
                try:
                    parsed = json.loads(raw.decode("utf-8")) if raw else None
                except (json.JSONDecodeError, UnicodeDecodeError):
                    parsed = None
                return {
                    "accepted": 200 <= int(response.status) < 300,
                    "status_code": int(response.status),
                    "response": parsed,
                }
        except HTTPError as exc:
            code = int(exc.code)
            body = exc.read()
            details = body.decode("utf-8", errors="replace") if body else ""
            raise OpenClawRequestError(
                f"OpenClaw CLI result callback rejected with HTTP {code}: {details}",
                kind="client_error" if 400 <= code < 500 else "server_error",
                status_code=code,
                retryable=code >= 500 or code == 429,
            ) from exc
        except socket.timeout as exc:
            raise OpenClawRequestError(
                f"Timeout reaching sidecar result callback after {self.timeout_sec}s",
                kind="timeout",
                retryable=True,
            ) from exc
        except URLError as exc:
            raise OpenClawRequestError(
                f"Unable to reach sidecar result callback: {exc.reason}",
                kind="connection_error",
                retryable=True,
            ) from exc

    def _callback_headers(self, callback: dict[str, Any]) -> dict[str, str]:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        extra_headers = callback.get("headers") or {}
        for key, value in extra_headers.items():
            headers[str(key)] = str(value)
        return headers

    def _resolve_openclaw_bin(self, configured: str | None) -> str:
        candidate = str(configured or "").strip()
        if candidate:
            return candidate

        env_candidate = str(os.environ.get("OPENCLAW_RUNTIME_CLI_BIN") or "").strip()
        if env_candidate:
            return env_candidate

        known_candidates = [
            "/home/ubuntu/.npm-global/bin/openclaw",
            "/usr/local/bin/openclaw",
            "/usr/bin/openclaw",
        ]
        for item in known_candidates:
            if Path(item).exists():
                return item
        return "openclaw"

    def _extract_json_document(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                stripped = "\n".join(lines[1:-1]).strip()

        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        lines = stripped.splitlines()
        for index, line in enumerate(lines):
            if not line.lstrip().startswith("{"):
                continue
            candidate = "\n".join(lines[index:]).strip()
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("JSON object not found")

    def _normalize_string_list(self, value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []


class OpenClawGatewayClient:
    def __init__(self, gateway_base_url: str, *, hooks_token: str = "", timeout_sec: float = 10.0) -> None:
        base_url = str(gateway_base_url).strip().rstrip("/")
        if not base_url:
            raise ValueError("gateway_base_url is required")
        self.gateway_base_url = base_url
        self.hooks_token = str(hooks_token).strip()
        self.timeout_sec = float(timeout_sec)

    def post_ingress_hook(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/hooks/openclaw/ingress", payload)

    def post_result_hook(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/hooks/openclaw/result", payload)

    def register_hooks(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post_json("/gateway/hooks/register", payload)

    def get_hook_status(self) -> dict[str, Any]:
        return self._get_json("/gateway/hooks/status")

    def probe_connectivity(self) -> dict[str, Any]:
        try:
            result = self.get_hook_status()
        except RuntimeError:
            return {
                "status": "unreachable",
                "ok": False,
                "status_code": None,
                "kind": "probe_error",
                "message": "Gateway hook status probe failed.",
            }
        return {
            "status": "reachable" if bool(result.get("ok")) else "unreachable",
            "ok": bool(result.get("ok")),
            "status_code": result.get("status_code"),
            "kind": None,
            "message": None,
        }

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.gateway_base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=self._request_headers(),
            method="POST",
        )
        return self._execute_request(request, error_prefix="OpenClaw gateway rejected hook POST")

    def _get_json(self, path: str) -> dict[str, Any]:
        request = Request(
            f"{self.gateway_base_url}{path}",
            headers=self._request_headers(include_content_type=False),
            method="GET",
        )
        return self._execute_request(request, error_prefix="OpenClaw gateway rejected hook status GET")

    def _request_headers(self, *, include_content_type: bool = True) -> dict[str, str]:
        headers: dict[str, str] = {}
        if include_content_type:
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.hooks_token:
            headers["X-OpenClaw-Hooks-Token"] = self.hooks_token
        return headers

    def _execute_request(self, request: Request, *, error_prefix: str) -> dict[str, Any]:
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read()
                try:
                    parsed = json.loads(raw.decode("utf-8")) if raw else None
                except (json.JSONDecodeError, UnicodeDecodeError):
                    parsed = None
                return {
                    "accepted": 200 <= int(response.status) < 300,
                    "ok": 200 <= int(response.status) < 300,
                    "status_code": int(response.status),
                    "response": parsed,
                }
        except HTTPError as exc:
            code = int(exc.code)
            body = exc.read()
            details = body.decode("utf-8", errors="replace") if body else ""
            if 400 <= code < 500:
                raise OpenClawRequestError(
                    f"{error_prefix} with HTTP {code}: {details}",
                    kind="client_error",
                    status_code=code,
                    retryable=code == 429,
                ) from exc
            raise OpenClawRequestError(
                f"{error_prefix} with HTTP {code}: {details}",
                kind="server_error",
                status_code=code,
                retryable=True,
            ) from exc
        except socket.timeout as exc:
            raise OpenClawRequestError(
                f"Timeout reaching OpenClaw gateway after {self.timeout_sec}s",
                kind="timeout",
                retryable=True,
            ) from exc
        except URLError as exc:
            raise OpenClawRequestError(
                f"Unable to reach OpenClaw gateway: {exc.reason}",
                kind="connection_error",
                retryable=True,
            ) from exc


class HttpOpenClawRuntimeBridge:
    def __init__(
        self,
        invoke_url: str,
        *,
        timeout_sec: float = 10.0,
        extra_headers: dict[str, str] | None = None,
        result_callback_url: str = "",
        hooks_token: str = "",
    ) -> None:
        url = str(invoke_url).strip()
        if not url:
            raise ValueError("invoke_url is required")
        self.invoke_url = url
        self.timeout_sec = float(timeout_sec)
        self.extra_headers = dict(extra_headers or {})
        self.result_callback_url = str(result_callback_url).strip()
        self.hooks_token = str(hooks_token).strip()

    def submit_invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = self._build_request_payload(payload)
        request = Request(
            self.invoke_url,
            data=json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8", **self.extra_headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read()
                try:
                    parsed = json.loads(raw.decode("utf-8")) if raw else None
                except (json.JSONDecodeError, UnicodeDecodeError):
                    parsed = None
                return {
                    "accepted": 200 <= int(response.status) < 300,
                    "status_code": int(response.status),
                    "response": parsed,
                }
        except HTTPError as exc:
            code = int(exc.code)
            body = exc.read()
            details = body.decode("utf-8", errors="replace") if body else ""
            if 400 <= code < 500:
                raise OpenClawRequestError(
                    f"OpenClaw runtime rejected invoke with HTTP {code}: {details}",
                    kind="client_error",
                    status_code=code,
                    retryable=code == 429,
                ) from exc
            raise OpenClawRequestError(
                f"OpenClaw runtime rejected invoke with HTTP {code}: {details}",
                kind="server_error",
                status_code=code,
                retryable=True,
            ) from exc
        except socket.timeout as exc:
            raise OpenClawRequestError(
                f"Timeout reaching OpenClaw runtime after {self.timeout_sec}s",
                kind="timeout",
                retryable=True,
            ) from exc
        except URLError as exc:
            raise OpenClawRequestError(
                f"Unable to reach OpenClaw runtime: {exc.reason}",
                kind="connection_error",
                retryable=True,
            ) from exc

    def _build_request_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = dict(payload)
        result_callback = self._build_result_callback_payload()
        if result_callback is None:
            return request_payload

        callbacks = dict(request_payload.get("callbacks") or {})
        callbacks["result"] = result_callback
        request_payload["callbacks"] = callbacks
        return request_payload

    def _build_result_callback_payload(self) -> dict[str, Any] | None:
        if not self.result_callback_url:
            return None

        payload: dict[str, Any] = {"url": self.result_callback_url}
        if self.hooks_token:
            payload["headers"] = {"X-OpenClaw-Hooks-Token": self.hooks_token}
        return payload

    def probe_connectivity(self) -> dict[str, Any]:
        request = Request(
            self.invoke_url,
            headers=self.extra_headers,
            method="OPTIONS",
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                return {
                    "status": "reachable",
                    "ok": True,
                    "status_code": int(response.status),
                    "kind": None,
                    "message": None,
                }
        except HTTPError as exc:
            reachable = 400 <= int(exc.code) < 500
            return {
                "status": "reachable" if reachable else "unreachable",
                "ok": reachable,
                "status_code": int(exc.code),
                "kind": "http_4xx" if reachable else "http_5xx",
                "message": f"{int(exc.code)} from runtime invoke endpoint.",
            }
        except URLError:
            return {
                "status": "unreachable",
                "ok": False,
                "status_code": None,
                "kind": "network_error",
                "message": "Unable to reach OpenClaw runtime.",
            }