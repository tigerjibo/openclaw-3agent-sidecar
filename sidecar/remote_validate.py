from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.request import urlopen

from .adapters.ingress import IngressAdapter
from .adapters.openclaw_runtime import CliOpenClawRuntimeBridge
from .config import load_config
from .models import get_task_by_id
from .service_runner import ServiceRunner


class _ProbingComponent(Protocol):
    def probe_connectivity(self) -> dict[str, object]: ...


def run_remote_validation(
    *,
    config: dict[str, Any] | None = None,
    gateway_client: _ProbingComponent | None = None,
    runtime_bridge: _ProbingComponent | None = None,
    dispatch_sample: bool = False,
    keep_db: bool = False,
    env_file: str | None = ".env",
) -> dict[str, Any]:
    merged = load_config()
    if env_file:
        _apply_env_file_defaults(merged, env_file)
    if config is not None:
        merged.update(config)

    tempdir_context = tempfile.TemporaryDirectory(prefix="openclaw-sidecar-remote-validate-")
    db_path = Path(tempdir_context.name) / "sidecar.sqlite3"
    runner = ServiceRunner(
        config={
            **merged,
            "host": str(merged.get("host") or "127.0.0.1"),
            "port": int(merged.get("port") or 0),
            "db_path": str(db_path),
            "maintenance_interval_sec": 0,
        }
    )
    if gateway_client is not None:
        runner._gateway_client = gateway_client  # type: ignore[assignment]
    if runtime_bridge is not None:
        runner._dispatcher.runtime_bridge = runtime_bridge  # type: ignore[assignment]

    try:
        runner.start()
        assert runner.http_service.base_url is not None
        if isinstance(runner._dispatcher.runtime_bridge, CliOpenClawRuntimeBridge):
            runner._dispatcher.runtime_bridge.result_callback_url = f"{runner.http_service.base_url}/hooks/openclaw/result"
        health = _get_json(f"{runner.http_service.base_url}/healthz")
        readiness = _get_json(f"{runner.http_service.base_url}/readyz")
        ops = _get_json(f"{runner.http_service.base_url}/ops/summary")

        dispatch_payload: dict[str, Any] | None = None
        if dispatch_sample:
            dispatch_payload = _dispatch_sample_task(runner)

        blocking_issues = _collect_blocking_issues(health=health, readiness=readiness, ops=ops, dispatch_payload=dispatch_payload)
        summary = {
            "ok": len(blocking_issues) == 0,
            "mode": "dispatch_sample" if dispatch_sample else "probe_only",
            "blocking_issues": blocking_issues,
            "health": health,
            "readiness": readiness,
            "ops": ops,
            "dispatch_sample": dispatch_payload,
            "db_path": str(db_path) if keep_db else "<temporary>",
        }
        return summary
    finally:
        runner.stop()
        if not keep_db:
            tempdir_context.cleanup()


def _dispatch_sample_task(runner: ServiceRunner) -> dict[str, Any]:
    ingress = IngressAdapter(runner._app)
    task_id = ingress.ingest(
        {
            "request_id": "req-remote-validate-001",
            "source": "openclaw",
            "source_user_id": "user-remote-validate",
            "entrypoint": "institutional_task",
            "title": "远端实施验证样例任务",
            "message": "验证 sidecar 是否能向远端 OpenClaw 正常提交 invoke。",
            "task_type_hint": "engineering",
        }
    )["task_id"]
    result = runner._dispatcher.dispatch_task(task_id)
    conn = runner._app.conn
    if conn is None:
        raise RuntimeError("service runner connection is not initialized")
    task = get_task_by_id(conn, task_id)
    return {
        "task_id": task_id,
        "dispatch_result": result,
        "task": task,
    }


def _collect_blocking_issues(
    *,
    health: dict[str, Any],
    readiness: dict[str, Any],
    ops: dict[str, Any],
    dispatch_payload: dict[str, Any] | None,
) -> list[str]:
    issues: list[str] = []
    if str(health.get("status") or "") in {"degraded", "failed"}:
        issues.append(f"health={health.get('status')}")
    if str(readiness.get("status") or "") != "ready":
        issues.append(f"readiness={readiness.get('status')}:{readiness.get('reason')}")

    ops_payload = cast(dict[str, Any], ops.get("ops") or {})
    integration = cast(dict[str, Any], ops_payload.get("integration") or {})
    integration_status = str(integration.get("status") or "")
    if integration_status in {"local_only", "partially_configured"}:
        issues.append(f"integration={integration_status}")

    gateway = cast(dict[str, Any], integration.get("gateway") or {})
    if gateway.get("hooks_enabled") and not gateway.get("hook_registration_ready"):
        issues.append(f"gateway_hook_registration={cast(dict[str, Any], gateway.get('hook_registration') or {}).get('status')}")

    runtime_invoke = cast(dict[str, Any], integration.get("runtime_invoke") or {})
    if runtime_invoke.get("invoke_url_configured") and not runtime_invoke.get("result_callback_ready"):
        missing = ",".join(str(item) for item in (runtime_invoke.get("missing_requirements") or []))
        issues.append(f"runtime_callback_missing={missing or 'unknown'}")

    probe = cast(dict[str, Any], integration.get("probe") or {})
    for component_name in ("gateway", "runtime_invoke"):
        component = cast(dict[str, Any], probe.get(component_name) or {})
        status = str(component.get("status") or "")
        if status == "unreachable":
            issues.append(f"{component_name}_probe=unreachable")

    if dispatch_payload is not None:
        dispatch_result = cast(dict[str, Any], dispatch_payload.get("dispatch_result") or {})
        if not bool(dispatch_result.get("dispatched")):
            issues.append(f"dispatch_sample={dispatch_result.get('reason') or 'failed'}")
            error_details = cast(dict[str, Any], dispatch_result.get("submission_error_details") or {})
            if str(error_details.get("stage") or "") == "callback":
                issues.append(
                    f"dispatch_sample=callback_failed:{str(dispatch_result.get('submission_error_kind') or 'unknown')}"
                )
        runtime_submission = cast(dict[str, Any], dispatch_result.get("runtime_submission") or {})
        runtime_response = cast(dict[str, Any], runtime_submission.get("response") or {})
        if str(runtime_response.get("result_status") or "") == "failed":
            issues.append(
                f"dispatch_sample=result_failed:{str(runtime_response.get('result_error_kind') or 'unknown')}"
            )

    return issues


def _get_json(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=15) as response:
        return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))


def _apply_env_file_defaults(config: dict[str, Any], env_file: str) -> None:
    path = Path(env_file)
    if not path.exists():
        return
    parsed = _parse_env_file(path)
    for key, value in parsed.items():
        env_name = f"OPENCLAW_{key.upper()}"
        if os.environ.get(env_name) is None:
            config[key] = value


def _parse_env_file(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized = key.strip()
        if not normalized.startswith("OPENCLAW_"):
            continue
        parsed[normalized[len("OPENCLAW_") :].lower()] = value.strip()
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate remote OpenClaw integration wiring and reachability.")
    parser.add_argument(
        "--dispatch-sample",
        action="store_true",
        help="Create one sample task and attempt a real runtime submission after the probe checks.",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the temporary SQLite DB on disk and print its path in the summary.",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Optional env file to preload OPENCLAW_* defaults before validation (default: .env).",
    )
    args = parser.parse_args(argv)

    summary = run_remote_validation(dispatch_sample=args.dispatch_sample, keep_db=args.keep_db, env_file=args.env_file)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if bool(summary.get("ok")) else 1


if __name__ == "__main__":
    raise SystemExit(main())