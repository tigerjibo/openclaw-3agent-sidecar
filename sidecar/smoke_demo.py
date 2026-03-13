from __future__ import annotations

import argparse
import json
import os
import tempfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterator, cast
from urllib.request import Request, urlopen

from .adapters.ingress import IngressAdapter
from .adapters.openclaw_runtime import HttpOpenClawRuntimeBridge
from .events import list_recent_events
from .models import get_task_by_id
from .service_runner import ServiceRunner


class FakeRuntimeCallbackServer:
    """Minimal fake OpenClaw runtime used by the smoke/demo flow."""

    def __init__(self, *, response_status: int = 202) -> None:
        self.requests: list[dict[str, object]] = []
        self.callback_responses: list[dict[str, object]] = []
        self._response_status = int(response_status)
        outer = self

        class Handler(BaseHTTPRequestHandler):
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
                outer._post_result_callback(payload)

                response = json.dumps(
                    {"accepted": 200 <= outer._response_status < 300, "submission_id": f"sub-{len(outer.requests):03d}"},
                    ensure_ascii=False,
                ).encode("utf-8")
                self.send_response(outer._response_status)
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

    def _post_result_callback(self, invoke_payload: dict[str, Any]) -> None:
        callback = cast(dict[str, Any], (invoke_payload.get("callbacks") or {}).get("result") or {})
        callback_url = str(callback.get("url") or "").strip()
        if not callback_url:
            return

        headers = cast(dict[str, str], callback.get("headers") or {})
        request = Request(
            callback_url,
            data=json.dumps(self._result_payload(invoke_payload), ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8", **headers},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            body = cast(dict[str, Any], json.loads(response.read().decode("utf-8")))
            self.callback_responses.append({"status": response.status, "body": body})

    def _result_payload(self, invoke_payload: dict[str, Any]) -> dict[str, Any]:
        role = str(invoke_payload["role"])
        output_by_role: dict[str, dict[str, object]] = {
            "coordinator": {
                "goal": "通过 smoke demo 跑通真实 HTTP invoke/result 闭环",
                "acceptance_criteria": ["coordinator/executor/reviewer 全链路完成"],
                "risk_notes": ["确保 result callback 不覆盖 dispatch 进度"],
                "proposed_steps": ["dispatch coordinator", "dispatch executor", "dispatch reviewer"],
            },
            "executor": {
                "result_summary": "executor 已通过 smoke demo 回写结果",
                "evidence": ["runtime-http-callback", "smoke-demo"],
                "open_issues": [],
                "followup_notes": [],
            },
            "reviewer": {
                "review_decision": "approve",
                "review_comment": "smoke demo 验证通过",
                "reasons": ["完整 HTTP callback 链路成功"],
                "required_rework": [],
                "residual_risk": "低",
            },
        }
        return {
            "invoke_id": invoke_payload["invoke_id"],
            "task_id": invoke_payload["task_id"],
            "role": role,
            "trace_id": invoke_payload["trace_id"],
            "status": "succeeded",
            "output": output_by_role[role],
        }


@contextmanager
def _temporary_env(overrides: dict[str, str]) -> Iterator[None]:
    previous: dict[str, str | None] = {key: os.environ.get(key) for key in overrides}
    try:
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def run_smoke_demo(*, keep_db: bool = False) -> dict[str, Any]:
    hooks_token = "smoke-demo-token"
    runtime = FakeRuntimeCallbackServer(response_status=202)
    tempdir_context = tempfile.TemporaryDirectory(prefix="openclaw-sidecar-smoke-")
    tempdir_path = Path(tempdir_context.name)
    db_path = tempdir_path / "sidecar.sqlite3"
    runner: ServiceRunner | None = None

    try:
        runtime.start()
        with _temporary_env({"OPENCLAW_HOOKS_TOKEN": hooks_token}):
            runner = ServiceRunner(
                config={
                    "host": "127.0.0.1",
                    "port": 0,
                    "db_path": str(db_path),
                    "default_runtime_mode": "legacy_single",
                    "maintenance_interval_sec": 0,
                    "hooks_token": hooks_token,
                    "runtime_invoke_url": f"{runtime.base_url}/invoke",
                }
            )
            runner.start()
            assert runner.http_service.base_url is not None

            runner._config["public_base_url"] = runner.http_service.base_url
            runner._dispatcher.runtime_bridge = HttpOpenClawRuntimeBridge(
                f"{runtime.base_url}/invoke",
                result_callback_url=f"{runner.http_service.base_url}/hooks/openclaw/result",
                hooks_token=hooks_token,
            )

            ingress = IngressAdapter(runner._app)
            task_id = ingress.ingest(
                {
                    "request_id": "req-smoke-demo-001",
                    "source": "openclaw",
                    "source_user_id": "user-smoke-demo",
                    "entrypoint": "institutional_task",
                    "title": "集成 smoke demo",
                    "message": "请通过真实 HTTP invoke/result 跑通最小 3-agent 闭环。",
                    "task_type_hint": "engineering",
                }
            )["task_id"]

            dispatches = [runner._dispatcher.dispatch_task(task_id) for _ in range(3)]
            health = _get_json(f"{runner.http_service.base_url}/healthz")
            readiness = _get_json(f"{runner.http_service.base_url}/readyz")
            ops = _get_json(f"{runner.http_service.base_url}/ops/summary")

            conn = runner._app.conn
            if conn is None:
                raise RuntimeError("service runner connection is not initialized")
            task = get_task_by_id(conn, task_id)
            events = list_recent_events(conn, task_id, limit=20)
            if task is None:
                raise RuntimeError(f"task not found after smoke demo: {task_id}")

            summary = {
                "ok": bool(task.get("state") == "done" and all(item.get("dispatched") for item in dispatches)),
                "task_id": task_id,
                "task_state": str(task.get("state") or ""),
                "current_role": task.get("current_role"),
                "dispatch_results": dispatches,
                "runtime_request_count": len(runtime.requests),
                "callback_response_count": len(runtime.callback_responses),
                "health": health,
                "readiness": readiness,
                "ops": ops,
                "recent_event_summaries": [str(event.get("summary") or "") for event in events],
                "db_path": str(db_path),
            }
            if not keep_db:
                summary["db_path"] = "<temporary>"
            return summary
    finally:
        if runner is not None:
            runner.stop()
        runtime.stop()
        if not keep_db:
            tempdir_context.cleanup()


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=5) as response:
        return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the sidecar real-HTTP smoke/demo flow.")
    parser.add_argument("--keep-db", action="store_true", help="Keep the temporary SQLite DB on disk and print its path.")
    args = parser.parse_args(argv)

    summary = run_smoke_demo(keep_db=args.keep_db)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if bool(summary.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())