from __future__ import annotations

from typing import Final

# Task lifecycle states
STATE_INBOX: Final[str] = "inbox"
STATE_TRIAGING: Final[str] = "triaging"
STATE_QUEUED: Final[str] = "queued"
STATE_EXECUTING: Final[str] = "executing"
STATE_REVIEWING: Final[str] = "reviewing"
STATE_REWORK: Final[str] = "rework"
STATE_DONE: Final[str] = "done"
STATE_CANCELLED: Final[str] = "cancelled"

TASK_STATES: Final[tuple[str, ...]] = (
    STATE_INBOX,
    STATE_TRIAGING,
    STATE_QUEUED,
    STATE_EXECUTING,
    STATE_REVIEWING,
    STATE_REWORK,
    STATE_DONE,
    STATE_CANCELLED,
)

# Core actions
ACTION_CREATE: Final[str] = "create"
ACTION_TRANSITION: Final[str] = "transition"
ACTION_REVIEW_APPROVE: Final[str] = "review_approve"
ACTION_REVIEW_REJECT: Final[str] = "review_reject"
ACTION_BLOCK: Final[str] = "block"
ACTION_UNBLOCK: Final[str] = "unblock"
ACTION_CONFIRM_DONE: Final[str] = "confirm_done"
ACTION_CANCEL: Final[str] = "cancel"

TASK_ACTIONS: Final[tuple[str, ...]] = (
    ACTION_CREATE,
    ACTION_TRANSITION,
    ACTION_REVIEW_APPROVE,
    ACTION_REVIEW_REJECT,
    ACTION_BLOCK,
    ACTION_UNBLOCK,
    ACTION_CONFIRM_DONE,
    ACTION_CANCEL,
)

# Event types
EVENT_TASK_CREATED: Final[str] = "task.created"
EVENT_TASK_TRANSITIONED: Final[str] = "task.transitioned"
EVENT_TASK_REVIEWED: Final[str] = "task.reviewed"
EVENT_TASK_BLOCKED: Final[str] = "task.blocked"
EVENT_TASK_UNBLOCKED: Final[str] = "task.unblocked"
EVENT_TASK_CANCELLED: Final[str] = "task.cancelled"
EVENT_TASK_DONE_CONFIRMED: Final[str] = "task.done_confirmed"

EVENT_TYPES: Final[tuple[str, ...]] = (
    EVENT_TASK_CREATED,
    EVENT_TASK_TRANSITIONED,
    EVENT_TASK_REVIEWED,
    EVENT_TASK_BLOCKED,
    EVENT_TASK_UNBLOCKED,
    EVENT_TASK_CANCELLED,
    EVENT_TASK_DONE_CONFIRMED,
)

# Canonical error schema
ERROR_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "ok",
    "error",
    "code",
    "message",
    "details",
)

# Canonical error codes
ERR_CONFLICT: Final[str] = "conflict"
ERR_INVALID_STATE: Final[str] = "invalid_state"
ERR_VALIDATION: Final[str] = "validation_error"
ERR_NOT_FOUND: Final[str] = "not_found"

# Ops contract constants
HEALTH_OK: Final[str] = "ok"
HEALTH_DEGRADED: Final[str] = "degraded"
HEALTH_FAILED: Final[str] = "failed"

HEALTH_STATES: Final[tuple[str, ...]] = (
    HEALTH_OK,
    HEALTH_DEGRADED,
    HEALTH_FAILED,
)

READINESS_READY: Final[str] = "ready"
READINESS_WARMING: Final[str] = "warming"
READINESS_BLOCKED: Final[str] = "blocked"

READINESS_STATES: Final[tuple[str, ...]] = (
    READINESS_READY,
    READINESS_WARMING,
    READINESS_BLOCKED,
)

ANOMALY_BLOCKED: Final[str] = "blocked"
ANOMALY_REVIEW_TIMEOUT: Final[str] = "review_timeout"
ANOMALY_EXECUTION_TIMEOUT: Final[str] = "execution_timeout"
ANOMALY_PENDING_HUMAN_CONFIRM: Final[str] = "pending_human_confirm"

ANOMALY_CATEGORIES: Final[tuple[str, ...]] = (
    ANOMALY_BLOCKED,
    ANOMALY_REVIEW_TIMEOUT,
    ANOMALY_EXECUTION_TIMEOUT,
    ANOMALY_PENDING_HUMAN_CONFIRM,
)

CONFIG_HOST: Final[str] = "host"
CONFIG_PORT: Final[str] = "port"
CONFIG_DB_PATH: Final[str] = "db_path"
CONFIG_MAINTENANCE_INTERVAL_SEC: Final[str] = "maintenance_interval_sec"
CONFIG_EXECUTING_TIMEOUT_SEC: Final[str] = "executing_timeout_sec"
CONFIG_REVIEWING_TIMEOUT_SEC: Final[str] = "reviewing_timeout_sec"
CONFIG_BLOCKED_ALERT_AFTER_SEC: Final[str] = "blocked_alert_after_sec"
CONFIG_DEFAULT_RUNTIME_MODE: Final[str] = "default_runtime_mode"
CONFIG_RUNTIME_INVOKE_URL: Final[str] = "runtime_invoke_url"
CONFIG_RUNTIME_CLI_TIMEOUT_SEC: Final[str] = "runtime_cli_timeout_sec"
CONFIG_INTEGRATION_PROBE_TTL_SEC: Final[str] = "integration_probe_ttl_sec"
CONFIG_HOOK_REGISTRATION_RETRY_SEC: Final[str] = "hook_registration_retry_sec"
CONFIG_HOOK_REGISTRATION_FAILURE_ALERT_AFTER: Final[str] = "hook_registration_failure_alert_after"
CONFIG_LOG_LEVEL: Final[str] = "log_level"
CONFIG_GATEWAY_BASE_URL: Final[str] = "gateway_base_url"
CONFIG_HOOKS_TOKEN: Final[str] = "hooks_token"
CONFIG_PUBLIC_BASE_URL: Final[str] = "public_base_url"

CONFIG_KEYS: Final[tuple[str, ...]] = (
    CONFIG_HOST,
    CONFIG_PORT,
    CONFIG_DB_PATH,
    CONFIG_MAINTENANCE_INTERVAL_SEC,
    CONFIG_EXECUTING_TIMEOUT_SEC,
    CONFIG_REVIEWING_TIMEOUT_SEC,
    CONFIG_BLOCKED_ALERT_AFTER_SEC,
    CONFIG_DEFAULT_RUNTIME_MODE,
    CONFIG_RUNTIME_INVOKE_URL,
    CONFIG_RUNTIME_CLI_TIMEOUT_SEC,
    CONFIG_INTEGRATION_PROBE_TTL_SEC,
    CONFIG_HOOK_REGISTRATION_RETRY_SEC,
    CONFIG_HOOK_REGISTRATION_FAILURE_ALERT_AFTER,
    CONFIG_LOG_LEVEL,
    CONFIG_GATEWAY_BASE_URL,
    CONFIG_HOOKS_TOKEN,
    CONFIG_PUBLIC_BASE_URL,
)
