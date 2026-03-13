from sidecar import __main__


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