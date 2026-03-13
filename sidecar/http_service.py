from __future__ import annotations

from datetime import datetime
import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from typing import Any, Optional
from urllib.parse import urlparse
import uuid

from .adapters.ingress import IngressAdapter
from .adapters.result import ResultAdapter
from .api import TaskKernelApiApp
from .briefing import build_brief
from .config import load_config
from .consistency import check_projection_consistency
from .detail_view import render_task_detail_html
from .events import list_recent_events
from .feishu_projection import project_task_to_feishu_record
from .metrics import compute_anomaly_summary, compute_metrics_snapshot, get_state_entry_time
from .models import get_task_by_id, list_tasks

logger = logging.getLogger(__name__)


class LocalTaskKernelHttpService:
    def __init__(self, *, app: TaskKernelApiApp, host: str = "127.0.0.1", port: int = 0):
        if host != "127.0.0.1":
            raise ValueError("LocalTaskKernelHttpService must bind to 127.0.0.1")
        self.app = app
        self.host = host
        self.port = port
        self._lock = threading.Lock()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.base_url: Optional[str] = None

    def start(self) -> None:
        if self._server is not None:
            return
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                service._handle_http(self)

            def do_POST(self) -> None:  # noqa: N802
                service._handle_http(self)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = HTTPServer((self.host, self.port), Handler)
        self.base_url = f"http://{self.host}:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None
        self.base_url = None

    def _handle_http(self, handler: BaseHTTPRequestHandler) -> None:
        parsed = urlparse(handler.path)
        path = parsed.path
        method = handler.command.upper()

        if method == "GET" and path == "/healthz":
            runner = getattr(self, "service_runner", None)
            self._write_json(handler, 200, runner.health_payload() if runner is not None else {"status": "ok"})
            return

        if method == "GET" and path == "/readyz":
            runner = getattr(self, "service_runner", None)
            self._write_json(handler, 200, runner.readiness_payload() if runner is not None else {"status": "ready"})
            return

        if method == "GET" and path == "/ops/summary":
            runner = getattr(self, "service_runner", None)
            payload = runner.ops_summary_payload() if runner is not None else {
                "status": "ok",
                "lifecycle_state": "unknown",
                "health": {"status": "ok"},
                "readiness": {"status": "ready"},
                "maintenance": {"status": "ok", "maintenance_enabled": False, "interval_sec": 0, "last_cycle": None},
            }
            self._write_json(handler, 200, {"status": "ok", "ops": payload})
            return

        if method == "GET" and path == "/runtime/maintenance":
            runner = getattr(self, "service_runner", None)
            payload = runner.maintenance_payload() if runner is not None else {"status": "ok", "maintenance_enabled": False, "interval_sec": 0, "last_cycle": None}
            self._write_json(handler, 200, {"status": "ok", "maintenance": payload})
            return

        if method == "POST" and path == "/runtime/ingress":
            with self._lock:
                payload = IngressAdapter(self.app).ingest(self._read_json_body(handler) or {}, channel="runtime")
            self._write_json(handler, 201 if bool(payload.get("created")) else 200, {"status": "ok", "data": payload})
            return

        if method == "POST" and path == "/runtime/result":
            with self._lock:
                payload = ResultAdapter(self.app).apply_result(self._read_json_body(handler) or {}, channel="runtime")
            self._write_json(handler, 200, {"status": "ok", "data": payload})
            return

        if method == "POST" and path.startswith("/runtime/unblock/"):
            task_id = path.rsplit("/", 1)[-1]
            body = self._read_json_body(handler) or {}
            body.setdefault("actor_role", "human")
            body.setdefault("trace_id", f"hitl-{uuid.uuid4()}")
            logger.info("hitl unblock requested task=%s trace=%s", task_id, body["trace_id"])
            with self._lock:
                response = self.app.handle_request("POST", f"/tasks/{task_id}/unblock", body=body)
            self._write_json(handler, response["status"], response["body"])
            return

        if method == "POST" and path == "/hooks/openclaw/ingress":
            if not self._authorize_openclaw_hook(handler):
                return
            with self._lock:
                payload = IngressAdapter(self.app).ingest(self._read_json_body(handler) or {}, channel="hook")
            self._write_json(handler, 201 if bool(payload.get("created")) else 200, {"status": "ok", "data": payload})
            return

        if method == "POST" and path == "/hooks/openclaw/result":
            if not self._authorize_openclaw_hook(handler):
                return
            with self._lock:
                payload = ResultAdapter(self.app).apply_result(self._read_json_body(handler) or {}, channel="hook")
            self._write_json(handler, 200, {"status": "ok", "data": payload})
            return

        if method == "GET" and path == "/exceptions":
            conn = self._require_conn()
            cfg = load_config()
            with self._lock:
                tasks = list_tasks(conn)
            exceptions: list[dict] = []
            for t in tasks:
                task = dict(t) if not isinstance(t, dict) else t
                projection = self._build_feishu_projection(task, cfg=cfg, conn=conn)
                issues = check_projection_consistency(task, projection=projection)
                for issue in issues:
                    exceptions.append({"task_id": task.get("task_id"), "category": issue["category"], "reason": issue["reason"]})
            self._write_json(handler, 200, {"ok": True, "data": exceptions})
            return

        if method == "GET" and path == "/metrics/summary":
            conn = self._require_conn()
            cfg = load_config()
            with self._lock:
                snapshot = compute_metrics_snapshot(conn, executing_timeout_sec=cfg["executing_timeout_sec"], reviewing_timeout_sec=cfg["reviewing_timeout_sec"])
                anomalies = compute_anomaly_summary(conn, executing_timeout_sec=cfg["executing_timeout_sec"], reviewing_timeout_sec=cfg["reviewing_timeout_sec"])
            self._write_json(handler, 200, {"ok": True, "data": {"snapshot": snapshot, "anomalies": anomalies}})
            return

        try:
            if method == "GET" and path.endswith("/projection/feishu"):
                status, body = self._projection_response(path.split("/")[2])
                self._write_json(handler, status, body)
                return
            if method == "GET" and path.endswith("/detail"):
                status, html = self._detail_response(path.split("/")[2])
                self._write_html(handler, status, html)
                return

            request_body = self._read_json_body(handler)
            with self._lock:
                response = self.app.handle_request(method, path, body=request_body)
            self._write_json(handler, response["status"], response["body"])
        except Exception as exc:  # pragma: no cover
            self._write_json(handler, 500, {"ok": False, "error": True, "code": "internal_error", "message": str(exc), "details": {}})

    def _projection_response(self, task_id: str) -> tuple[int, dict[str, Any]]:
        conn = self._require_conn()
        with self._lock:
            task = get_task_by_id(conn, task_id)
        if task is None:
            return 404, {"ok": False, "error": True, "code": "not_found", "message": f"task not found: {task_id}", "details": {"task_id": task_id}}
        cfg = load_config()
        record = self._build_feishu_projection(task, cfg=cfg, conn=conn)
        return 200, {"ok": True, "data": record}

    def _detail_response(self, task_id: str) -> tuple[int, str]:
        conn = self._require_conn()
        with self._lock:
            task = get_task_by_id(conn, task_id)
            recent_events = list_recent_events(conn, task_id, limit=10)
        if task is None:
            return 404, f"<html><body><h1>task not found: {task_id}</h1></body></html>"
        brief = build_brief(
            task_type=str(task.get("task_type") or "general"),
            goal=str(task.get("goal") or task.get("title") or "完成该任务"),
            acceptance_criteria=_normalize_list_field(task.get("acceptance_criteria")) or ["任务结果可验证", "状态流转符合内核约束"],
            risk_notes=_risk_notes_for_task(task),
            proposed_steps=["查看任务上下文与最近事件", "按当前角色推进下一个受限动作", "完成后更新内核状态"],
        )
        html = render_task_detail_html(task=task, brief=brief, recent_events=list(reversed(recent_events)))
        return 200, html

    def _read_json_body(self, handler: BaseHTTPRequestHandler) -> Optional[dict[str, Any]]:
        content_length = int(handler.headers.get("Content-Length", "0") or "0")
        if content_length <= 0:
            return None
        raw = handler.rfile.read(content_length)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def _write_json(self, handler: BaseHTTPRequestHandler, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    def _write_html(self, handler: BaseHTTPRequestHandler, status: int, html: str) -> None:
        payload = html.encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(payload)))
        handler.end_headers()
        handler.wfile.write(payload)

    def _authorize_openclaw_hook(self, handler: BaseHTTPRequestHandler) -> bool:
        cfg = load_config()
        expected_token = str(cfg.get("hooks_token") or "").strip()
        provided_token = str(handler.headers.get("X-OpenClaw-Hooks-Token") or "").strip()
        if expected_token and provided_token == expected_token:
            return True
        self._write_json(
            handler,
            401,
            {
                "ok": False,
                "error": True,
                "code": "unauthorized",
                "message": "invalid or missing hooks token",
                "details": {},
            },
        )
        return False

    def _require_conn(self):
        conn = self.app.conn
        if conn is None:
            raise RuntimeError("TaskKernelApiApp connection is not initialized")
        return conn

    def _build_feishu_projection(self, task: dict[str, Any], *, cfg: dict[str, Any], conn) -> dict[str, Any]:
        now_ts = int(datetime.now().timestamp())
        updated_at_ts = _parse_sqlite_timestamp(task.get("updated_at")) or now_ts
        state = str(task.get("state") or "")
        state_entered = get_state_entry_time(conn, str(task.get("task_id") or ""), state)
        state_entered_ts = int(state_entered.timestamp()) if state_entered is not None else updated_at_ts
        block_since_ts = _parse_sqlite_timestamp(task.get("block_since"))
        return project_task_to_feishu_record(task, executing_timeout_sec=int(cfg["executing_timeout_sec"]), reviewing_timeout_sec=int(cfg["reviewing_timeout_sec"]), blocked_alert_after_sec=int(cfg["blocked_alert_after_sec"]), now_ts=now_ts, state_entered_ts=state_entered_ts, block_since_ts=block_since_ts)


def _parse_sqlite_timestamp(value: object) -> Optional[int]:
    if value in (None, ""):
        return None
    return int(datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").timestamp())


def _normalize_list_field(value: object) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return [line.strip() for line in text.splitlines() if line.strip()]


def _risk_notes_for_task(task: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if task.get("requires_human_confirm"):
        notes.append("该任务需要人工确认后才算闭环")
    if task.get("blocked"):
        notes.append(f"当前阻塞原因：{task.get('block_reason') or '未填写'}")
    if not notes:
        notes.append("保持看板投影与任务内核一致，不要绕过状态机")
    return notes
