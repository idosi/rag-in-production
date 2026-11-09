"""Tests for exercise 3d-2. Do not edit; make them pass by editing my_ready.py.

Run:   uv run pytest exercises/ready -q
"""

import psycopg

from exercises.ready.my_ready import readiness


def test_1_index_with_chunks_is_ready():
    assert readiness(lambda: 745) == (200, {"status": "ok", "chunks": 745})


def test_2_empty_index_is_not_ready_and_says_what_to_do():
    status, body = readiness(lambda: 0)
    assert status == 503
    assert body["status"] == "not_ready"
    assert "ingest" in body["reason"]


def test_3_database_error_is_503_not_a_crash():
    def broken():
        raise psycopg.OperationalError("connection refused")

    status, body = readiness(broken)
    assert status == 503
    assert body == {"status": "not_ready", "reason": "database unreachable"}


def test_4_the_error_text_never_reaches_the_public_body():
    def broken():
        raise psycopg.OperationalError(
            'connection to server at "ep-cool-river-123.neon.tech", user "neondb_owner" failed'
        )

    _, body = readiness(broken)
    assert "neondb_owner" not in str(body)
    assert "ep-cool-river" not in str(body)


def test_5_count_is_asked_exactly_once():
    calls = []

    def count():
        calls.append(1)
        return 3

    readiness(count)
    assert len(calls) == 1  # one DB round trip per probe, not two
