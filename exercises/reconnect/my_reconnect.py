"""EXERCISE 3d-3: survive the database going to sleep.

Run the tests:   uv run pytest exercises/reconnect -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY (do this exercise AFTER you have seen the bug live, guide section 7)
    The API opens ONE connection at startup and keeps it forever (db.py, pipeline.py).
    On your laptop that is fine: Postgres never goes away.

    Neon Free scales to zero: after 5 minutes without queries the compute is suspended
    and every open connection is CLOSED by the server. An idle open connection does not
    keep it awake. Cloud Run keeps an idle container alive longer than 5 minutes, so:

        16:00  question -> fine
        16:05  Neon suspends, our connection is now dead (we don't know yet)
        16:08  question -> psycopg.OperationalError -> 500
        16:09  question -> 500 again. And forever, until the container is replaced.

    The fix: when a query fails because the CONNECTION is broken, open a new connection
    and try once more. Neon wakes up in a few hundred milliseconds on the new connection.

THE SPEC
    Reconnector(connect, retry_on=(psycopg.OperationalError,))
        connect    a function with no arguments that opens a new connection
                   (real code: lambda: db.connect(url))
        Opens the first connection immediately, in __init__ (fail fast at startup).

    .conn            the current connection
    .run(fn)         calls fn(conn) and returns its result.
                     If fn raises one of retry_on: close the old connection (ignore any
                     error from close, it is broken anyway), open a new one, call fn ONCE
                     more with the new connection. If that fails too, let the error out.
                     Any other exception (a bug in our SQL, a ValueError) is NOT retried.
    .reconnects      how many times a new connection was opened after a failure
                     (0 at start). Worth exposing: a number that climbs is a signal.
    .close()         close the current connection

HINTS (open one at a time, only when stuck)
    1. except self.retry_on:   works when retry_on is a tuple of exception classes.
    2. Why only ONE retry? If the database is really down, retrying in a loop holds the
       request (and a thread) for a long time and hammers the database. Fail, and let the
       caller (or /ready) report it.
    3. Why not retry ProgrammingError (e.g. a typo in a table name)? Because a new
       connection gives the same error. Retry only what a retry can fix.
    4. Is it safe to run a query twice? For SELECT, yes. For our writes too: replace_document
       is one transaction (delete + insert), so a retry gives the same end state. Remember to
       ask this question about every retry you write: "is this operation idempotent?"
    5. (reviewer, no test) Two threads can fail at the same moment and both reconnect.
       A threading.Lock around "close + connect" prevents opening two connections and
       leaking one. Bonus: inside the lock, reconnect only if self.conn is still the
       connection that failed (another thread may have replaced it already).
"""

from collections.abc import Callable
from typing import Any

import psycopg


class Reconnector:
    def __init__(
        self,
        connect: Callable[[], Any],
        retry_on: tuple[type[BaseException], ...] = (psycopg.OperationalError,),
    ):
        raise NotImplementedError("your code here")

    def run(self, fn: Callable[[Any], Any]) -> Any:
        raise NotImplementedError("your code here")

    def close(self) -> None:
        raise NotImplementedError("your code here")
