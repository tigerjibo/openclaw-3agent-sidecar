"""Tests for SQLite WAL mode and busy_timeout pragmas."""
from __future__ import annotations

import tempfile
import os

from sidecar.storage import connect, init_db


def test_wal_mode_enabled_on_persistent_db():
    """After init_db on a file-backed DB, journal_mode should be WAL."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        conn = connect(db_path)
        init_db(conn)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        conn.close()


def test_busy_timeout_set():
    """After init_db, busy_timeout should be 5000 ms."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        conn = connect(db_path)
        init_db(conn)
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        assert timeout == 5000
        conn.close()


def test_wal_mode_noop_on_memory_db():
    """In-memory DB cannot use WAL; init_db should not crash."""
    conn = connect(":memory:")
    init_db(conn)
    # Memory DBs report 'memory' for journal_mode; just ensure no error
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode in ("memory", "wal")
    conn.close()
