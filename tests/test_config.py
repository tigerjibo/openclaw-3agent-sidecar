from sidecar.config import load_config


def test_load_config_accepts_legacy_sidecar_db_path_alias(monkeypatch) -> None:
    monkeypatch.delenv("OPENCLAW_DB_PATH", raising=False)
    monkeypatch.setenv("SIDECAR_DB_PATH", "runtime/sidecar.sqlite3")

    cfg = load_config()

    assert cfg["db_path"] == "runtime/sidecar.sqlite3"


def test_load_config_prefers_canonical_openclaw_env_over_legacy_alias(monkeypatch) -> None:
    monkeypatch.setenv("SIDECAR_DB_PATH", "runtime/legacy.sqlite3")
    monkeypatch.setenv("OPENCLAW_DB_PATH", "runtime/canonical.sqlite3")

    cfg = load_config()

    assert cfg["db_path"] == "runtime/canonical.sqlite3"


def test_load_config_reads_integration_probe_ttl_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_INTEGRATION_PROBE_TTL_SEC", "42")

    cfg = load_config()

    assert cfg["integration_probe_ttl_sec"] == 42


def test_load_config_reads_public_base_url_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_PUBLIC_BASE_URL", "https://sidecar.example.com/base/")

    cfg = load_config()

    assert cfg["public_base_url"] == "https://sidecar.example.com/base/"


def test_load_config_reads_hook_registration_retry_interval_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_HOOK_REGISTRATION_RETRY_SEC", "123")

    cfg = load_config()

    assert cfg["hook_registration_retry_sec"] == 123


def test_load_config_reads_hook_registration_failure_alert_threshold_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLAW_HOOK_REGISTRATION_FAILURE_ALERT_AFTER", "4")

    cfg = load_config()

    assert cfg["hook_registration_failure_alert_after"] == 4