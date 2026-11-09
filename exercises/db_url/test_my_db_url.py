"""Tests for exercise 3d-1. Do not edit; make them pass by editing my_db_url.py.

Run:   uv run pytest exercises/db_url -q
Read them in order: each one adds one idea.
"""

import pytest

from exercises.db_url.my_db_url import redact, require_tls

LOCAL = "postgresql://rag:rag@localhost:5432/rag"
NEON = (
    "postgresql://neondb_owner:npg_S3cr3t@ep-cool-river-123.eu-central-1.aws.neon.tech"
    "/neondb?sslmode=require&channel_binding=require"
)
NEON_NO_TLS = (
    "postgresql://neondb_owner:npg_S3cr3t@ep-cool-river-123.eu-central-1.aws.neon.tech/neondb"
)


def test_1_redact_hides_the_password():
    assert "npg_S3cr3t" not in redact(NEON)
    assert "neondb_owner:***@" in redact(NEON)


def test_2_redact_keeps_everything_else():
    assert redact(NEON) == NEON.replace("npg_S3cr3t", "***")
    assert redact(LOCAL) == "postgresql://rag:***@localhost:5432/rag"


def test_3_redact_without_a_password_changes_nothing():
    assert redact("postgresql://localhost/rag") == "postgresql://localhost/rag"


def test_4_local_hosts_need_no_tls():
    require_tls(LOCAL)  # no exception = pass
    require_tls("postgresql://rag:rag@127.0.0.1:5432/rag")
    require_tls("postgresql://rag:rag@db:5432/rag")  # the docker compose service name


def test_5_remote_host_with_sslmode_require_is_fine():
    require_tls(NEON)
    require_tls(NEON_NO_TLS + "?sslmode=verify-full")


def test_6_remote_host_without_sslmode_is_refused():
    with pytest.raises(ValueError) as e:
        require_tls(NEON_NO_TLS)
    assert "ep-cool-river-123" in str(e.value)  # says WHICH database
    assert "npg_S3cr3t" not in str(e.value)  # but never the password


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer"])
def test_7_modes_that_can_fall_back_to_plain_text_are_refused(mode):
    with pytest.raises(ValueError):
        require_tls(NEON_NO_TLS + f"?sslmode={mode}")
