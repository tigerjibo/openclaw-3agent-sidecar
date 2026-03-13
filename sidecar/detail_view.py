from __future__ import annotations

from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "templates" / "task_detail.html"


def render_task_detail_html(*, task: dict[str, object], brief: dict[str, object], recent_events: list[dict[str, object]]) -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    acceptance_items = "".join(f"<li>{item}</li>" for item in brief.get("acceptance_criteria", []))
    risk_items = "".join(f"<li>{item}</li>" for item in brief.get("risk_notes", []))
    step_items = "".join(f"<li>{item}</li>" for item in brief.get("proposed_steps", []))
    event_items = "".join(f"<li>{item.get('summary', '')}</li>" for item in recent_events)

    return template.format(
        task_id=task.get("task_id", ""),
        title=task.get("title", ""),
        task_type=task.get("task_type", ""),
        state=task.get("state", ""),
        current_role=task.get("current_role", ""),
        goal=brief.get("goal", task.get("goal", "")),
        review_decision=task.get("review_decision", ""),
        review_comment=task.get("review_comment", ""),
        acceptance_items=acceptance_items,
        risk_items=risk_items,
        step_items=step_items,
        event_items=event_items,
    )
