from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

MODE_LEGACY_SINGLE: Final[str] = "legacy_single"
MODE_THREE_AGENT_SHADOW: Final[str] = "three_agent_shadow"
MODE_THREE_AGENT_ACTIVE: Final[str] = "three_agent_active"

VALID_RUNTIME_MODES: Final[tuple[str, ...]] = (
    MODE_LEGACY_SINGLE,
    MODE_THREE_AGENT_SHADOW,
    MODE_THREE_AGENT_ACTIVE,
)

ROLE_NAMES: Final[tuple[str, ...]] = (
    "coordinator",
    "executor",
    "reviewer",
)


@dataclass
class RuntimeModeController:
    production_model: str
    mode: str = MODE_LEGACY_SINGLE
    role_models: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self.role_models = {role_name: self.production_model for role_name in ROLE_NAMES}

    def snapshot(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "role_models": dict(self.role_models),
        }

    def set_role_model(self, role_name: str, model_name: str) -> None:
        if role_name not in ROLE_NAMES:
            raise ValueError(f"Unsupported role: {role_name}")
        if not model_name:
            raise ValueError("model_name must be non-empty")
        self.role_models[role_name] = model_name

    def switch_mode(self, new_mode: str, *, force: bool = False) -> dict[str, object]:
        if new_mode not in VALID_RUNTIME_MODES:
            raise ValueError(f"Unsupported runtime mode: {new_mode}")
        if new_mode == self.mode:
            return self.snapshot()
        if not self._is_allowed_transition(self.mode, new_mode, force=force):
            raise ValueError(f"Unsafe runtime mode transition: {self.mode} -> {new_mode}")
        self.mode = new_mode
        return self.snapshot()

    def _is_allowed_transition(self, old_mode: str, new_mode: str, *, force: bool) -> bool:
        if old_mode == MODE_LEGACY_SINGLE:
            return new_mode == MODE_THREE_AGENT_SHADOW
        if old_mode == MODE_THREE_AGENT_SHADOW:
            return new_mode in (MODE_LEGACY_SINGLE, MODE_THREE_AGENT_ACTIVE)
        if old_mode == MODE_THREE_AGENT_ACTIVE:
            if new_mode == MODE_THREE_AGENT_SHADOW:
                return True
            if new_mode == MODE_LEGACY_SINGLE:
                return force
        return False
