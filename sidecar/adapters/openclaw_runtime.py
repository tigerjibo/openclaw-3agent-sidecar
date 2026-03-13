from __future__ import annotations

import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class OpenClawRuntimeBridge(Protocol):
    def submit_invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...


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
                parsed = json.loads(raw.decode("utf-8")) if raw else None
                return {
                    "accepted": 200 <= int(response.status) < 300,
                    "ok": 200 <= int(response.status) < 300,
                    "status_code": int(response.status),
                    "response": parsed,
                }
        except HTTPError as exc:
            body = exc.read()
            details = body.decode("utf-8", errors="replace") if body else ""
            raise RuntimeError(f"{error_prefix} with HTTP {exc.code}: {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Unable to reach OpenClaw gateway: {exc.reason}") from exc


class HttpOpenClawRuntimeBridge:
    def __init__(self, invoke_url: str, *, timeout_sec: float = 10.0, extra_headers: dict[str, str] | None = None) -> None:
        url = str(invoke_url).strip()
        if not url:
            raise ValueError("invoke_url is required")
        self.invoke_url = url
        self.timeout_sec = float(timeout_sec)
        self.extra_headers = dict(extra_headers or {})

    def submit_invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.invoke_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8", **self.extra_headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_sec) as response:
                raw = response.read()
                parsed = json.loads(raw.decode("utf-8")) if raw else None
                return {
                    "accepted": 200 <= int(response.status) < 300,
                    "status_code": int(response.status),
                    "response": parsed,
                }
        except HTTPError as exc:
            body = exc.read()
            details = body.decode("utf-8", errors="replace") if body else ""
            raise RuntimeError(f"OpenClaw runtime rejected invoke with HTTP {exc.code}: {details}") from exc
        except URLError as exc:
            raise RuntimeError(f"Unable to reach OpenClaw runtime: {exc.reason}") from exc

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