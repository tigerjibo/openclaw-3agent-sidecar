import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from sidecar.adapters.agent_invoke import AgentInvokeAdapter
from sidecar.adapters.ingress import IngressAdapter
from sidecar.adapters.openclaw_runtime import HttpOpenClawRuntimeBridge, OpenClawGatewayClient
from sidecar.api import TaskKernelApiApp
from sidecar.events import list_recent_events
from sidecar.http_service import LocalTaskKernelHttpService
from sidecar.models import get_task_by_id
from sidecar.runtime_mode import RuntimeModeController
from sidecar.storage import connect, init_db


class _JsonCaptureServer:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                outer.requests.append(
                    {
                        "method": "GET",
                        "path": self.path,
                        "headers": {key: value for key, value in self.headers.items()},
                    }
                )
                response = json.dumps({"ok": True, "hooks": [{"name": "openclaw-ingress", "enabled": True}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def do_POST(self) -> None:  # noqa: N802
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
                payload = json.loads(raw.decode("utf-8"))
                outer.requests.append(
                    {
                        "method": "POST",
                        "path": self.path,
                        "headers": {key: value for key, value in self.headers.items()},
                        "payload": payload,
                    }
                )
                response = json.dumps({"accepted": True, "submission_id": "sub-http-001"}).encode("utf-8")
                self.send_response(202)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


class _OptionsStatusServer:
    def __init__(self, *, options_status: int) -> None:
        self.requests: list[dict[str, object]] = []
        self._options_status = int(options_status)
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self) -> None:  # noqa: N802
                outer.requests.append(
                    {
                        "method": "OPTIONS",
                        "path": self.path,
                        "headers": {key: value for key, value in self.headers.items()},
                    }
                )
                self.send_response(outer._options_status)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = HTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def _build_app() -> TaskKernelApiApp:
    conn = connect(":memory:")
    init_db(conn)
    controller = RuntimeModeController(production_model="default")
    return TaskKernelApiApp(runtime_mode_controller=controller, conn=conn)


def _post_json(url: str, payload: dict[str, object]) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        body = cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
        return response.status, body


def _post_json_with_headers(url: str, payload: dict[str, object], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8", **headers},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        body = cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
        return response.status, body


def test_http_openclaw_runtime_bridge_posts_invoke_payload() -> None:
    server = _JsonCaptureServer()
    server.start()

    try:
        bridge = HttpOpenClawRuntimeBridge(f"{server.base_url}/invoke")
        response = bridge.submit_invoke(
            {
                "invoke_id": "inv:test:coordinator:v1:a1",
                "task_id": "task-test",
                "role": "coordinator",
                "agent_id": "coordinator",
                "input": {"message": "hello"},
            }
        )
    finally:
        server.stop()

    assert response["accepted"] is True
    assert response["status_code"] == 202
    assert response["response"] == {"accepted": True, "submission_id": "sub-http-001"}
    assert server.requests[0]["payload"]["task_id"] == "task-test"
    assert server.requests[0]["payload"]["role"] == "coordinator"


def test_openclaw_gateway_client_posts_ingress_hook_with_token() -> None:
    server = _JsonCaptureServer()
    server.start()

    try:
        client = OpenClawGatewayClient(server.base_url, hooks_token="hook-secret")
        response = client.post_ingress_hook(
            {
                "request_id": "req-gateway-client-ingress-001",
                "source": "openclaw",
                "entrypoint": "institutional_task",
                "title": "gateway ingress hook",
                "message": "通过 gateway client 发送 ingress hook。",
            }
        )
    finally:
        server.stop()

    assert response["accepted"] is True
    assert response["status_code"] == 202
    assert server.requests[0]["path"] == "/hooks/openclaw/ingress"
    assert server.requests[0]["payload"]["request_id"] == "req-gateway-client-ingress-001"


def test_openclaw_gateway_client_posts_result_hook_with_token() -> None:
    server = _JsonCaptureServer()
    server.start()

    try:
        client = OpenClawGatewayClient(server.base_url, hooks_token="hook-secret")
        response = client.post_result_hook(
            {
                "invoke_id": "inv:test:coordinator:v1:a1",
                "task_id": "task-test",
                "role": "coordinator",
                "status": "succeeded",
                "output": {"goal": "hook result"},
            }
        )
    finally:
        server.stop()

    assert response["accepted"] is True
    assert response["status_code"] == 202
    assert server.requests[0]["path"] == "/hooks/openclaw/result"
    assert server.requests[0]["payload"]["invoke_id"] == "inv:test:coordinator:v1:a1"


def test_openclaw_gateway_client_registers_hooks_with_token() -> None:
    server = _JsonCaptureServer()
    server.start()

    try:
        client = OpenClawGatewayClient(server.base_url, hooks_token="hook-secret")
        response = client.register_hooks(
            {
                "ingress_url": "http://127.0.0.1:9600/hooks/openclaw/ingress",
                "result_url": "http://127.0.0.1:9600/hooks/openclaw/result",
            }
        )
    finally:
        server.stop()

    assert response["accepted"] is True
    assert response["status_code"] == 202
    assert server.requests[0]["path"] == "/gateway/hooks/register"
    assert server.requests[0]["headers"]["X-Openclaw-Hooks-Token"] == "hook-secret"
    assert server.requests[0]["payload"]["ingress_url"] == "http://127.0.0.1:9600/hooks/openclaw/ingress"


def test_openclaw_gateway_client_fetches_hook_status() -> None:
    server = _JsonCaptureServer()
    server.start()

    try:
        client = OpenClawGatewayClient(server.base_url, hooks_token="hook-secret")
        response = client.get_hook_status()
    finally:
        server.stop()

    assert response["ok"] is True
    assert response["status_code"] == 200
    assert response["response"] == {"ok": True, "hooks": [{"name": "openclaw-ingress", "enabled": True}]}
    assert server.requests[0]["method"] == "GET"
    assert server.requests[0]["path"] == "/gateway/hooks/status"


def test_openclaw_gateway_client_probe_connectivity_reports_reachable() -> None:
    server = _JsonCaptureServer()
    server.start()

    try:
        client = OpenClawGatewayClient(server.base_url, hooks_token="hook-secret")
        response = client.probe_connectivity()
    finally:
        server.stop()

    assert response == {
        "status": "reachable",
        "ok": True,
        "status_code": 200,
        "kind": None,
        "message": None,
    }
    assert server.requests[0]["method"] == "GET"
    assert server.requests[0]["path"] == "/gateway/hooks/status"


def test_openclaw_gateway_client_probe_connectivity_reports_unreachable_on_error() -> None:
    class FailingGatewayClient(OpenClawGatewayClient):
        def get_hook_status(self) -> dict[str, Any]:
            raise RuntimeError("boom")

    client = FailingGatewayClient("http://127.0.0.1:1", hooks_token="hook-secret")

    assert client.probe_connectivity() == {
        "status": "unreachable",
        "ok": False,
        "status_code": None,
        "kind": "probe_error",
        "message": "Gateway hook status probe failed.",
    }


def test_http_openclaw_runtime_bridge_probe_connectivity_reports_reachable() -> None:
    server = _OptionsStatusServer(options_status=204)
    server.start()

    try:
        bridge = HttpOpenClawRuntimeBridge(f"{server.base_url}/invoke")
        response = bridge.probe_connectivity()
    finally:
        server.stop()

    assert response == {
        "status": "reachable",
        "ok": True,
        "status_code": 204,
        "kind": None,
        "message": None,
    }
    assert server.requests[0]["method"] == "OPTIONS"
    assert server.requests[0]["path"] == "/invoke"


def test_http_openclaw_runtime_bridge_probe_connectivity_treats_4xx_as_reachable() -> None:
    server = _OptionsStatusServer(options_status=405)
    server.start()

    try:
        bridge = HttpOpenClawRuntimeBridge(f"{server.base_url}/invoke")
        response = bridge.probe_connectivity()
    finally:
        server.stop()

    assert response == {
        "status": "reachable",
        "ok": True,
        "status_code": 405,
        "kind": "http_4xx",
        "message": "405 from runtime invoke endpoint.",
    }


def test_http_openclaw_runtime_bridge_probe_connectivity_reports_unreachable_on_network_error() -> None:
    bridge = HttpOpenClawRuntimeBridge("http://127.0.0.1:1/invoke")

    assert bridge.probe_connectivity() == {
        "status": "unreachable",
        "ok": False,
        "status_code": None,
        "kind": "network_error",
        "message": "Unable to reach OpenClaw runtime.",
    }


def test_runtime_ingress_endpoint_creates_task() -> None:
    app = _build_app()
    service = LocalTaskKernelHttpService(app=app, host="127.0.0.1", port=0)

    try:
        service.start()
        assert service.base_url is not None
        status, body = _post_json(
            f"{service.base_url}/runtime/ingress",
            {
                "request_id": "req-runtime-ingress-001",
                "source": "openclaw",
                "source_user_id": "user-runtime-ingress",
                "entrypoint": "institutional_task",
                "title": "从官方 runtime 进入 sidecar",
                "message": "把 ingress 走 HTTP 接口送进来。",
                "task_type_hint": "engineering",
            },
        )
    finally:
        service.stop()

    assert status == 201
    assert body["status"] == "ok"
    assert body["data"]["created"] is True
    conn = app.conn
    assert conn is not None
    task = get_task_by_id(conn, str(body["data"]["task_id"]))
    assert task is not None
    assert task["source"] == "openclaw"
    events = list_recent_events(conn, str(body["data"]["task_id"]), limit=10)
    assert any(event["summary"] == "ingress accepted via runtime: 从官方 runtime 进入 sidecar" for event in events)


def test_runtime_result_endpoint_applies_role_output() -> None:
    app = _build_app()
    service = LocalTaskKernelHttpService(app=app, host="127.0.0.1", port=0)
    ingress = IngressAdapter(app)
    invoke = AgentInvokeAdapter(app)
    task_id = ingress.ingest(
        {
            "request_id": "req-runtime-result-001",
            "source": "openclaw",
            "source_user_id": "user-runtime-result",
            "entrypoint": "institutional_task",
            "title": "从官方 runtime 回写 result",
            "message": "让 coordinator 的结果通过 HTTP 回调写回 sidecar。",
            "task_type_hint": "engineering",
        }
    )["task_id"]

    try:
        service.start()
        assert service.base_url is not None
        status, body = _post_json(
            f"{service.base_url}/runtime/result",
            {
                "invoke_id": invoke.build_invoke(task_id, role="coordinator")["invoke_id"],
                "task_id": task_id,
                "role": "coordinator",
                "status": "succeeded",
                "output": {
                    "goal": "打通 runtime result 回写",
                    "acceptance_criteria": ["callback works"],
                    "risk_notes": [],
                    "proposed_steps": ["ingress", "invoke", "result"],
                },
            },
        )
    finally:
        service.stop()

    assert status == 200
    assert body["status"] == "ok"
    conn = app.conn
    assert conn is not None
    task = get_task_by_id(conn, task_id)
    assert task is not None
    assert task["state"] == "queued"
    assert task["current_role"] == "executor"
    assert task["goal"] == "打通 runtime result 回写"
    events = list_recent_events(conn, task_id, limit=10)
    assert any(event["summary"] == "coordinator result received via runtime: succeeded" for event in events)


def test_openclaw_ingress_hook_requires_matching_hooks_token(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_HOOKS_TOKEN", "hook-secret")
    app = _build_app()
    service = LocalTaskKernelHttpService(app=app, host="127.0.0.1", port=0)

    try:
        service.start()
        assert service.base_url is not None
        with_headers = _post_json_with_headers(
            f"{service.base_url}/hooks/openclaw/ingress",
            {
                "request_id": "req-openclaw-hook-ingress-001",
                "source": "openclaw",
                "source_user_id": "user-openclaw-hook",
                "entrypoint": "institutional_task",
                "title": "通过 hook token 进入 sidecar",
                "message": "带 token 的 ingress hook 应该被接受。",
                "task_type_hint": "engineering",
            },
            {"X-OpenClaw-Hooks-Token": "hook-secret"},
        )
    finally:
        service.stop()

    status, body = with_headers
    assert status == 201
    assert body["status"] == "ok"
    conn = app.conn
    assert conn is not None
    task = get_task_by_id(conn, str(body["data"]["task_id"]))
    assert task is not None
    assert task["source"] == "openclaw"
    events = list_recent_events(conn, str(body["data"]["task_id"]), limit=10)
    assert any(event["summary"] == "ingress accepted via hook: 通过 hook token 进入 sidecar" for event in events)


def test_openclaw_ingress_hook_rejects_missing_or_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_HOOKS_TOKEN", "hook-secret")
    app = _build_app()
    service = LocalTaskKernelHttpService(app=app, host="127.0.0.1", port=0)

    try:
        service.start()
        assert service.base_url is not None
        request = Request(
            f"{service.base_url}/hooks/openclaw/ingress",
            data=json.dumps(
                {
                    "request_id": "req-openclaw-hook-ingress-unauthorized",
                    "source": "openclaw",
                    "source_user_id": "user-openclaw-hook",
                    "entrypoint": "institutional_task",
                    "title": "未经授权的 hook",
                    "message": "不带 token 的请求应该被拒绝。",
                    "task_type_hint": "engineering",
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            urlopen(request, timeout=5)
        except HTTPError as exc:
            body = cast(dict[str, Any], json.loads(exc.read().decode("utf-8")))
            status = exc.code
        else:  # pragma: no cover
            raise AssertionError("expected hook ingress request to be rejected")
    finally:
        service.stop()

    assert status == 401
    assert body["code"] == "unauthorized"


def test_openclaw_result_hook_requires_matching_hooks_token(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_HOOKS_TOKEN", "hook-secret")
    app = _build_app()
    service = LocalTaskKernelHttpService(app=app, host="127.0.0.1", port=0)
    ingress = IngressAdapter(app)
    invoke = AgentInvokeAdapter(app)
    task_id = ingress.ingest(
        {
            "request_id": "req-openclaw-hook-result-001",
            "source": "openclaw",
            "source_user_id": "user-openclaw-hook-result",
            "entrypoint": "institutional_task",
            "title": "通过 result hook 回写 sidecar",
            "message": "带 token 的 result hook 应该被接受。",
            "task_type_hint": "engineering",
        }
    )["task_id"]

    try:
        service.start()
        assert service.base_url is not None
        status, body = _post_json_with_headers(
            f"{service.base_url}/hooks/openclaw/result",
            {
                "invoke_id": invoke.build_invoke(task_id, role="coordinator")["invoke_id"],
                "task_id": task_id,
                "role": "coordinator",
                "status": "succeeded",
                "output": {
                    "goal": "打通 hook result 回写",
                    "acceptance_criteria": ["hook callback works"],
                    "risk_notes": [],
                    "proposed_steps": ["ingress hook", "invoke", "result hook"],
                },
            },
            {"X-OpenClaw-Hooks-Token": "hook-secret"},
        )
    finally:
        service.stop()

    assert status == 200
    assert body["status"] == "ok"
    conn = app.conn
    assert conn is not None
    task = get_task_by_id(conn, task_id)
    assert task is not None
    assert task["state"] == "queued"
    assert task["current_role"] == "executor"
    assert task["goal"] == "打通 hook result 回写"
    events = list_recent_events(conn, task_id, limit=10)
    assert any(event["summary"] == "coordinator result received via hook: succeeded" for event in events)


def test_openclaw_result_hook_rejects_missing_or_invalid_token(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_HOOKS_TOKEN", "hook-secret")
    app = _build_app()
    service = LocalTaskKernelHttpService(app=app, host="127.0.0.1", port=0)
    ingress = IngressAdapter(app)
    invoke = AgentInvokeAdapter(app)
    task_id = ingress.ingest(
        {
            "request_id": "req-openclaw-hook-result-unauthorized",
            "source": "openclaw",
            "source_user_id": "user-openclaw-hook-result",
            "entrypoint": "institutional_task",
            "title": "未经授权的 result hook",
            "message": "不带 token 的 result hook 应该被拒绝。",
            "task_type_hint": "engineering",
        }
    )["task_id"]

    try:
        service.start()
        assert service.base_url is not None
        request = Request(
            f"{service.base_url}/hooks/openclaw/result",
            data=json.dumps(
                {
                    "invoke_id": invoke.build_invoke(task_id, role="coordinator")["invoke_id"],
                    "task_id": task_id,
                    "role": "coordinator",
                    "status": "succeeded",
                    "output": {
                        "goal": "不应写回",
                        "acceptance_criteria": [],
                        "risk_notes": [],
                        "proposed_steps": [],
                    },
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            urlopen(request, timeout=5)
        except HTTPError as exc:
            body = cast(dict[str, Any], json.loads(exc.read().decode("utf-8")))
            status = exc.code
        else:  # pragma: no cover
            raise AssertionError("expected hook result request to be rejected")
    finally:
        service.stop()

    assert status == 401
    assert body["code"] == "unauthorized"
