from __future__ import annotations

from sidecar.adapters.ingress import IngressAdapter
from sidecar.config import load_config
from sidecar.models import get_task_by_id
from sidecar.service_runner import ServiceRunner


def _create_task(runner: ServiceRunner, request_id: str) -> str:
    ingress = IngressAdapter(runner._app)
    return ingress.ingest(
        {
            "request_id": request_id,
            "source": "feishu",
            "source_user_id": "user-service-runner-persistence",
            "entrypoint": "institutional_task",
            "title": "persistent task",
            "message": "用于 service runner 持久化测试。",
            "task_type_hint": "engineering",
        }
    )["task_id"]


def test_load_config_reads_db_path_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_DB_PATH", "runtime/sidecar.sqlite3")

    config = load_config()

    assert config["db_path"] == "runtime/sidecar.sqlite3"


def test_service_runner_uses_persistent_db_path_across_restart(tmp_path) -> None:
    db_path = tmp_path / "state" / "sidecar.sqlite3"
    config = {
        "host": "127.0.0.1",
        "port": 0,
        "default_runtime_mode": "legacy_single",
        "db_path": str(db_path),
    }

    first_runner = ServiceRunner(config=config)
    try:
        first_runner.start()
        task_id = _create_task(first_runner, request_id="req-service-runner-persistent")
    finally:
        first_runner.stop()

    assert db_path.exists()

    second_runner = ServiceRunner(config=config)
    try:
        conn = second_runner._app.conn
        assert conn is not None
        task = get_task_by_id(conn, task_id)
    finally:
        second_runner.stop()

    assert task is not None
    assert task["task_id"] == task_id
    assert task["title"] == "persistent task"
