from __future__ import annotations

import os
from typing import Any

from .contracts import CONFIG_KEYS

_DEFAULTS: dict[str, Any] = {
    # Core (always needed)
    "host": "127.0.0.1",
    "port": 9600,
    "db_path": ":memory:",  # Override with OPENCLAW_DB_PATH for persistence
    "maintenance_interval_sec": 5.0,
    "executing_timeout_sec": 3600,
    "reviewing_timeout_sec": 1800,
    "blocked_alert_after_sec": 600,
    "default_runtime_mode": "legacy_single",
    "log_level": "INFO",
    # Integration (only for OpenClaw integration mode)
    "runtime_invoke_url": "",
    "runtime_cli_timeout_sec": 120.0,
    "runtime_submit_retry_delay_sec": 30.0,
    "runtime_submit_max_attempts": 3,
    "integration_probe_ttl_sec": 30.0,
    "hook_registration_retry_sec": 300.0,
    "hook_registration_failure_alert_after": 3,
    "gateway_base_url": "",
    "hooks_token": "",
    "public_base_url": "",
}

_INT_KEYS = {"port", "executing_timeout_sec", "reviewing_timeout_sec", "blocked_alert_after_sec", "hook_registration_failure_alert_after", "runtime_submit_max_attempts"}
_FLOAT_KEYS = {"maintenance_interval_sec", "runtime_cli_timeout_sec", "runtime_submit_retry_delay_sec", "integration_probe_ttl_sec", "hook_registration_retry_sec"}
_ALIASES: dict[str, tuple[str, ...]] = {
    "db_path": ("SIDECAR_DB_PATH",),
    "log_level": ("SIDECAR_LOG_LEVEL",),
}


def load_config() -> dict[str, Any]:
    """Load runtime configuration from env vars with safe defaults."""
    cfg: dict[str, Any] = dict(_DEFAULTS)
    for key in CONFIG_KEYS:
        env_name = f"OPENCLAW_{key.upper()}"
        env_val = os.environ.get(env_name)
        if env_val is None:
            for alias in _ALIASES.get(key, ()):
                env_val = os.environ.get(alias)
                if env_val is not None:
                    break
        if env_val is not None:
            if key in _INT_KEYS:
                try:
                    cfg[key] = int(env_val)
                except ValueError as exc:
                    raise ValueError(f"Invalid integer for {env_name}: {env_val!r}") from exc
            elif key in _FLOAT_KEYS:
                try:
                    cfg[key] = float(env_val)
                except ValueError as exc:
                    raise ValueError(f"Invalid number for {env_name}: {env_val!r}") from exc
            else:
                cfg[key] = env_val
    return cfg
