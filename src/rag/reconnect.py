"""Survive a database connection that died (step 3d). Written by Ido as exercise 3d-3.

THE BUG IT FIXES (seen live on Cloud Run, see docs/learning/03d section 7)
    The API opens ONE connection at startup and keeps it. Neon (free plan) suspends the
    database after 5 minutes without queries and CLOSES every open connection. The
    container stays alive, so every later question hit the dead connection:
        psycopg.OperationalError: the connection is closed   ->  HTTP 500, until a restart.

THE FIX
    When a query fails with a connection error, open a NEW connection and run the query
    ONE more time. Neon wakes up within a few hundred milliseconds of the new connection.

WHY ONLY ONE RETRY, AND ONLY ON OperationalError
    A typo in the SQL fails the same way on a new connection, so retrying only delays it.
    And if the database is really down, a retry loop would hold a thread and hit a database
    that is trying to recover. One retry fixes the common case (an old connection);
    /ready and the alerts handle the real outage.
    Retrying is safe because every query that goes through here is a SELECT.

THREADS
    FastAPI runs requests in a thread pool, all sharing one Reconnector. Two threads can fail
    on the same dead connection at the same moment. The lock plus the `self.conn is conn`
    check make sure only the first one replaces it; the second sees that someone already
    did, and uses the new connection (it must not close the new one).
"""

import threading
from collections.abc import Callable
from typing import Any

import psycopg


class Reconnector:
    def __init__(
        self,
        connect: Callable[[], Any],
        retry_on: tuple[type[BaseException], ...] = (psycopg.OperationalError,),
    ):
        self.connect = connect
        self.retry_on = retry_on
        self.conn = connect()  # opened now: a database that is down fails the startup
        self.reconnects = 0  # a number that keeps climbing is a signal worth alerting on
        self.lock = threading.Lock()

    def run(self, fn: Callable[[Any], Any]) -> Any:
        """Call fn(connection); if the connection is dead, replace it and call fn once more."""
        conn = self.conn  # the connection THIS call uses (not self.conn, which can change)
        try:
            return fn(conn)
        except self.retry_on:
            with self.lock:
                if self.conn is conn:  # nobody replaced it yet
                    self.reconnects += 1
                    try:
                        self.conn.close()
                    except Exception:
                        pass  # it is broken anyway
                    self.conn = self.connect()
            return fn(self.conn)

    def close(self) -> None:
        with self.lock:
            self.conn.close()
