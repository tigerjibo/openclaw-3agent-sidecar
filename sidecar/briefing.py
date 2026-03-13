from __future__ import annotations


def build_brief(
    *,
    task_type: str,
    goal: str,
    acceptance_criteria: list[str],
    risk_notes: list[str],
    proposed_steps: list[str],
) -> dict[str, object]:
    normalized_task_type = task_type.strip()
    normalized_goal = goal.strip()
    normalized_acceptance_criteria = [item.strip() for item in acceptance_criteria if item.strip()]
    normalized_risk_notes = [item.strip() for item in risk_notes if item.strip()]
    normalized_proposed_steps = [item.strip() for item in proposed_steps if item.strip()]

    if not normalized_task_type:
        raise ValueError("task_type is required")
    if not normalized_goal:
        raise ValueError("goal is required")
    if not normalized_acceptance_criteria:
        raise ValueError("acceptance_criteria is required")
    if not normalized_proposed_steps:
        raise ValueError("proposed_steps is required")

    return {
        "task_type": normalized_task_type,
        "goal": normalized_goal,
        "acceptance_criteria": normalized_acceptance_criteria,
        "risk_notes": normalized_risk_notes,
        "proposed_steps": normalized_proposed_steps,
    }
