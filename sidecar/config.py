from __future__ import annotations

import os
from typing import Any

from .contracts import CONFIG_KEYS

_DEFAULTS: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 9600,
    "executing_timeout_sec": 3600,
    "reviewing_timeout_sec": 1800,
    "blocked_alert_after_sec": 600,
    "default_runtime_mode": "legacy_single",
}

_INT_KEYS = {"port", "executing_timeout_sec", "reviewing_timeout_sec", "blocked_alert_after_sec"}


def load_config() -> dict[str, Any]:
    """Load runtime configuration from env vars with safe defaults."""
    cfg: dict[str, Any] = dict(_DEFAULTS)
    for key in CONFIG_KEYS:
        env_name = f"OPENCLAW_{key.upper()}"
        env_val = os.environ.get(env_name)
        if env_val is not None:
            if key in _INT_KEYS:
                try:
                    cfg[key] = int(env_val)
                except ValueError as exc:
                    raise ValueError(f"Invalid integer for {env_name}: {env_val!r}") from exc
            else:
                cfg[key] = env_val
    return cfg
