"""Reconnector (step 3d): a dead connection is replaced and the query retried once.

No real database in most of these: fake connections that we kill by hand."""

import psycopg
import pytest

from rag.reconnect import Reconnector


class FakeConn:
    def __init__(self, n):
        self.n = n  # which connection this is: 1, 2, 3...
        self.closed = False

    def close(self):
        self.closed = True


class FakeDatabase:
    """Hands out numbered connections, and counts how many were opened."""

    def __init__(self):
        self.opened = []

    def connect(self):
        conn = FakeConn(len(self.opened) + 1)
        self.opened.append(conn)
        return conn


def dead_on(*numbers):
    """A query that fails with a connection error on the given connection numbers."""

    def query(conn):
        if conn.n in numbers:
            raise psycopg.OperationalError("server closed the connection unexpectedly")
        return f"rows from connection {conn.n}"

    return query


def test_1_opens_the_connection_at_startup():
    db = FakeDatabase()
    r = Reconnector(db.connect)
    assert len(db.opened) == 1
    assert r.conn is db.opened[0]
    assert r.reconnects == 0


def test_2_run_passes_the_connection_and_returns_the_result():
    db = FakeDatabase()
    r = Reconnector(db.connect)
    assert r.run(dead_on()) == "rows from connection 1"
    assert r.run(dead_on()) == "rows from connection 1"
    assert len(db.opened) == 1  # healthy connection is reused, not reopened


def test_3_a_dead_connection_is_replaced_and_the_query_retried():
    db = FakeDatabase()
    r = Reconnector(db.connect)
    assert r.run(dead_on(1)) == "rows from connection 2"
    assert r.conn is db.opened[1]
    assert r.reconnects == 1


def test_4_the_old_connection_is_closed_even_if_close_fails():
    db = FakeDatabase()
    r = Reconnector(db.connect)

    def close_fails():
        raise psycopg.OperationalError("already gone")

    r.conn.close = close_fails
    assert r.run(dead_on(1)) == "rows from connection 2"  # close() raising did not stop us


def test_5_only_one_retry_then_the_error_comes_out():
    db = FakeDatabase()
    r = Reconnector(db.connect)
    with pytest.raises(psycopg.OperationalError):
        r.run(dead_on(1, 2, 3, 4))
    assert len(db.opened) == 2  # the first + ONE reconnect, not a loop


def test_6_other_errors_are_not_retried():
    db = FakeDatabase()
    r = Reconnector(db.connect)

    def typo(conn):
        raise psycopg.errors.UndefinedTable('relation "chunkz" does not exist')

    with pytest.raises(psycopg.errors.UndefinedTable):
        r.run(typo)
    assert len(db.opened) == 1  # a new connection would not fix a typo
    assert r.reconnects == 0


def test_7_retry_on_can_be_changed():
    db = FakeDatabase()
    r = Reconnector(db.connect, retry_on=(TimeoutError,))

    def slow_once(conn):
        if conn.n == 1:
            raise TimeoutError
        return "ok"

    assert r.run(slow_once) == "ok"


def test_8_close_closes_the_current_connection():
    db = FakeDatabase()
    r = Reconnector(db.connect)
    r.run(dead_on(1))
    r.close()
    assert db.opened[1].closed


def test_9_threads_failing_on_the_same_dead_connection_replace_it_only_once():
    # Eight requests hit the dead connection at the same moment (the FastAPI thread pool).
    # Only the first may replace it; the others must notice and use the new one, instead of
    # closing it and opening yet another (which would cut the first thread's query).
    import threading

    db = FakeDatabase()
    r = Reconnector(db.connect)
    barrier = threading.Barrier(8)
    results = []

    def query(conn):
        if conn.n == 1:
            barrier.wait(timeout=5)  # everyone fails on connection 1 together
            raise psycopg.OperationalError("the connection is closed")
        return conn.n

    threads = [threading.Thread(target=lambda: results.append(r.run(query))) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [2] * 8
    assert r.reconnects == 1
    assert len(db.opened) == 2
    assert not db.opened[1].closed


def test_10_a_real_killed_connection_is_survived_by_the_store(conn, test_database, embedder):
    # The Neon scenario for real: the server closes our connection (pg_terminate_backend plays
    # the part of "the compute was suspended"), and the next search still works.
    from rag.db import connect
    from rag.store import ChunkStore

    reconnector = Reconnector(lambda: connect(test_database))
    store = ChunkStore(reconnector)
    assert store.count_chunks() == 0  # the connection works

    with conn.cursor() as cur:  # `conn` is the fixture's separate admin connection
        cur.execute("SELECT pg_terminate_backend(%s)", (reconnector.conn.info.backend_pid,))

    assert store.count_chunks() == 0  # no exception: it reconnected
    assert store.search(embedder.embed_query("anything"), 3) == []
    assert reconnector.reconnects == 1
    reconnector.close()
