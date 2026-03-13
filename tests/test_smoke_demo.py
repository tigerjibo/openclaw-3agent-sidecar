from __future__ import annotations

from sidecar.smoke_demo import run_smoke_demo


def test_run_smoke_demo_completes_real_http_closed_loop() -> None:
    summary = run_smoke_demo()

    assert summary["ok"] is True
    assert summary["task_state"] == "done"
    assert summary["runtime_request_count"] == 3
    assert summary["callback_response_count"] == 3
    assert summary["health"]["status"] == "ok"
    assert summary["readiness"]["status"] == "ready"
    assert summary["ops"]["ops"]["integration"]["status"] == "runtime_invoke_ready"
    assert summary["ops"]["ops"]["integration"]["runtime_invoke"]["result_callback_ready"] is True
    assert any(text == "reviewer result received via hook: succeeded" for text in summary["recent_event_summaries"])