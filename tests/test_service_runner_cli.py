import json
from urllib.request import urlopen

from sidecar import __main__
from sidecar.service_runner import ServiceRunner


def test_main_starts_and_stops_service_runner_cleanly() -> None:
    calls: list[str] = []

    class FakeRunner:
        def start(self) -> None:
            calls.append("start")

        def stop(self) -> None:
            calls.append("stop")

    def fake_sleep(_: float) -> None:
        raise KeyboardInterrupt()

    exit_code = __main__.main(runner_factory=FakeRunner, sleep_fn=fake_sleep)

    assert exit_code == 0
    assert calls == ["start", "stop"]


def test_service_runner_smoke_endpoints_report_local_only_mode() -> None:
    runner = ServiceRunner(
        config={
            "host": "127.0.0.1",
            "port": 0,
            "default_runtime_mode": "legacy_single",
            "maintenance_interval_sec": 0,
        }
    )

    try:
        runner.start()
        assert runner.http_service.base_url is not None

        with urlopen(f"{runner.http_service.base_url}/healthz") as response:
            health = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{runner.http_service.base_url}/readyz") as response:
            readiness = json.loads(response.read().decode("utf-8"))
        with urlopen(f"{runner.http_service.base_url}/ops/summary") as response:
            ops = json.loads(response.read().decode("utf-8"))
    finally:
        runner.stop()

    assert health["status"] == "ok"
    assert readiness == {"status": "ready"}
    assert ops["status"] == "ok"
    assert ops["ops"]["integration"]["status"] == "local_only"
    assert ops["ops"]["integration"]["runtime_invoke"]["bridge_available"] is False