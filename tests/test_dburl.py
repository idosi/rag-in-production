"""The database URL helpers (step 3d): no password in logs, no plain-text remote database."""

import logging

import psycopg
import pytest

from rag import db
from rag.config import Settings
from rag.dburl import redact, require_tls

NEON = "postgresql://neondb_owner:npg_S3cr3t@ep-cool-river-123.eu-central-1.aws.neon.tech/neondb"


def test_redact_hides_only_the_password():
    assert (
        redact(NEON + "?sslmode=require") == NEON.replace("npg_S3cr3t", "***") + "?sslmode=require"
    )
    assert redact("postgresql://localhost/rag") == "postgresql://localhost/rag"


def test_local_hosts_need_no_tls_and_remote_hosts_do():
    require_tls("postgresql://rag:rag@db:5432/rag")
    require_tls(NEON + "?sslmode=require")
    for bad in ("", "?sslmode=prefer", "?sslmode=disable"):
        with pytest.raises(ValueError) as e:
            require_tls(NEON + bad)
        assert "npg_S3cr3t" not in str(e.value)


def test_a_repeated_sslmode_cannot_smuggle_plain_text_through():
    # libpq uses the LAST value, so every value must be safe, not just the first.
    with pytest.raises(ValueError):
        require_tls(NEON + "?sslmode=require&sslmode=disable")
    with pytest.raises(ValueError):
        require_tls(NEON + "?sslmode=disable&sslmode=require")


def test_connect_refuses_a_remote_url_without_tls_before_opening_anything():
    with pytest.raises(ValueError):
        db.connect(NEON)  # no network is touched: the check comes first


def test_settings_never_print_the_database_password():
    s = Settings(database_url=NEON, _env_file=None)
    assert "npg_S3cr3t" not in repr(s) and "npg_S3cr3t" not in str(s)
    assert s.database_url.get_secret_value() == NEON


def test_connect_logs_the_url_without_the_password(caplog):
    caplog.set_level(logging.INFO, logger="rag.db")
    with pytest.raises(psycopg.OperationalError):  # unreachable host: we only care what was logged
        db.connect("postgresql://u:topsecret@127.0.0.1:1/x")
    assert "topsecret" not in caplog.text
    assert "u:***@127.0.0.1" in caplog.text
