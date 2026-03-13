from __future__ import annotations

from typing import Final

from sidecar import contracts

_ALLOWED_TRANSITIONS: Final[dict[str, tuple[str, ...]]] = {
    contracts.STATE_INBOX: (contracts.STATE_TRIAGING, contracts.STATE_CANCELLED),
    contracts.STATE_TRIAGING: (contracts.STATE_QUEUED, contracts.STATE_CANCELLED),
    contracts.STATE_QUEUED: (contracts.STATE_EXECUTING, contracts.STATE_CANCELLED),
    contracts.STATE_EXECUTING: (contracts.STATE_REVIEWING, contracts.STATE_CANCELLED),
    contracts.STATE_REVIEWING: (
        contracts.STATE_DONE,
        contracts.STATE_REWORK,
        contracts.STATE_CANCELLED,
    ),
    contracts.STATE_REWORK: (contracts.STATE_EXECUTING, contracts.STATE_CANCELLED),
    contracts.STATE_DONE: (),
    contracts.STATE_CANCELLED: (),
}

_STATE_OWNER_ROLE: Final[dict[str, str]] = {
    contracts.STATE_INBOX: "coordinator",
    contracts.STATE_TRIAGING: "coordinator",
    contracts.STATE_QUEUED: "executor",
    contracts.STATE_EXECUTING: "executor",
    contracts.STATE_REVIEWING: "reviewer",
    contracts.STATE_REWORK: "executor",
}


def allowed_next_states(state: str) -> tuple[str, ...]:
    return _ALLOWED_TRANSITIONS.get(state, ())


def is_valid_transition(old_state: str, new_state: str) -> bool:
    return new_state in allowed_next_states(old_state)


def can_actor_transition(actor_role: str, old_state: str, new_state: str) -> bool:
    if not is_valid_transition(old_state, new_state):
        return False

    if old_state in (contracts.STATE_DONE, contracts.STATE_CANCELLED):
        return False

    owner = _STATE_OWNER_ROLE.get(old_state)
    return owner == actor_role


def apply_rework_priority_flags(
    *,
    old_state: str,
    new_state: str,
    rework_priority_available: bool,
    rework_priority_used: bool,
) -> tuple[bool, bool]:
    """Apply one-time rework priority rule."""
    available = rework_priority_available
    used = rework_priority_used

    if old_state == contracts.STATE_REVIEWING and new_state == contracts.STATE_REWORK:
        if not used:
            available = True
        else:
            available = False

    if old_state == contracts.STATE_REWORK and new_state == contracts.STATE_EXECUTING:
        if available:
            available = False
            used = True

    return available, used
