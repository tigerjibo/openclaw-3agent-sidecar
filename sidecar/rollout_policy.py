"""Pure rollout decision helper for the sidecar."""
from __future__ import annotations

from typing import Any

_MAX_ERROR_RATE = 0.10
_MAX_QUEUE_DELAY_SEC = 60
_MAX_REJECT_RATE = 0.10

_ROLLBACK_ERROR_RATE = 0.20
_ROLLBACK_QUEUE_DELAY_SEC = 90
_ROLLBACK_REJECT_RATE = 0.20


def _metrics_healthy(metrics: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if metrics.get("error_rate", 0) > _MAX_ERROR_RATE:
        reasons.append(f"error_rate {metrics['error_rate']:.2%} exceeds {_MAX_ERROR_RATE:.0%}")
    if metrics.get("queue_delay_sec", 0) > _MAX_QUEUE_DELAY_SEC:
        reasons.append(f"queue_delay {metrics['queue_delay_sec']}s exceeds {_MAX_QUEUE_DELAY_SEC}s")
    if metrics.get("reject_rate", 0) > _MAX_REJECT_RATE:
        reasons.append(f"reject_rate {metrics['reject_rate']:.2%} exceeds {_MAX_REJECT_RATE:.0%}")
    return len(reasons) == 0, reasons


def _metrics_critical(metrics: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if metrics.get("error_rate", 0) > _ROLLBACK_ERROR_RATE:
        reasons.append(f"error_rate {metrics['error_rate']:.2%} exceeds rollback threshold {_ROLLBACK_ERROR_RATE:.0%}")
    if metrics.get("queue_delay_sec", 0) > _ROLLBACK_QUEUE_DELAY_SEC:
        reasons.append(f"queue_delay {metrics['queue_delay_sec']}s exceeds rollback threshold {_ROLLBACK_QUEUE_DELAY_SEC}s")
    if metrics.get("reject_rate", 0) > _ROLLBACK_REJECT_RATE:
        reasons.append(f"reject_rate {metrics['reject_rate']:.2%} exceeds rollback threshold {_ROLLBACK_REJECT_RATE:.0%}")
    return len(reasons) > 0, reasons


def evaluate_rollout(*, current_mode: str, target_mode: str, metrics: dict[str, Any], check_only: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if check_only:
        result["check_only"] = True

    if target_mode == "legacy_single":
        result["decision"] = "allow"
        result["rationale"] = "Rollback to legacy_single is always permitted."
        return result

    if current_mode == "legacy_single" and target_mode == "three_agent_shadow":
        result["decision"] = "allow"
        result["rationale"] = "Shadow mode carries no production risk; transition allowed."
        return result

    if current_mode == "three_agent_shadow" and target_mode == "three_agent_active":
        healthy, reasons = _metrics_healthy(metrics)
        if healthy:
            result["decision"] = "allow"
            result["rationale"] = "All metrics within healthy thresholds; safe to activate."
        else:
            result["decision"] = "hold"
            result["rationale"] = "Metrics not healthy: " + "; ".join(reasons)
        return result

    result["decision"] = "hold"
    result["rationale"] = f"Unrecognized transition {current_mode} -> {target_mode}; holding."
    return result


def recommend_action(*, current_mode: str, metrics: dict[str, Any]) -> dict[str, Any]:
    critical, reasons = _metrics_critical(metrics)
    if critical:
        return {
            "recommendation": "rollback",
            "rationale": "Critical thresholds exceeded: " + "; ".join(reasons),
        }

    return {
        "recommendation": "hold",
        "rationale": "Metrics within acceptable range; no action needed.",
    }
