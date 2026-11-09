"""EXERCISE 3d-2: "is the process alive?" and "can it answer?" are two different questions.

Run the tests:   uv run pytest exercises/ready -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    Today /health counts the chunks and answers 200 {"status": "ok", "chunks": N}.
    Two problems in the cloud:

    1. With an EMPTY index (you deployed but forgot to ingest into Neon) it says "ok",
       and every question gets "I couldn't find this in the docs". Looks healthy, is useless.
       We found exactly this on day 1 (make ask before make ingest).
    2. If the database is down, /health raises -> 500. A platform that uses /health as a
       LIVENESS check then RESTARTS the container. Restarting does not fix the database;
       it only adds a 20-second cold start on top of the outage, for every instance.

    So we split it, like Kubernetes and Cloud Run do:
        GET /health   liveness:  the process runs. Never touches the DB. Always 200.
        GET /ready    readiness: the DB answers AND the index is not empty. 200 or 503.

    This exercise writes the decision behind /ready, as a plain function (easy to test).
    Wiring it into api.py is my part.

THE SPEC
    readiness(count_chunks) -> (status_code, body)
        count_chunks   a function with no arguments that returns the number of chunks
                       (api.py passes store.count_chunks). It may raise.

        N > 0          -> 200, {"status": "ok", "chunks": N}
        0              -> 503, {"status": "not_ready", "reason": "index is empty: run ingest"}
        it raises      -> 503, {"status": "not_ready", "reason": "database unreachable"}

    The body of the error case must NOT contain the exception text: a psycopg error message
    can include the host and user name, and /ready is a public URL.

HINTS (open one at a time, only when stuck)
    1. try: n = count_chunks()  /  except Exception: ...
       Catching Exception (not a bare except) is right here: this is a boundary that must
       always return an answer, and Exception does not swallow Ctrl+C (KeyboardInterrupt).
    2. Log the real error for yourself before returning the generic body:
       log.warning("readiness: database check failed: %s", type(e).__name__)
       Which part of the error is safe to log? The type name is. The message may not be.
    3. Return a tuple: return 200, {"status": "ok", "chunks": n}
"""

import logging
from collections.abc import Callable

log = logging.getLogger("rag.api")


def readiness(count_chunks: Callable[[], int]) -> tuple[int, dict]:
    raise NotImplementedError("your code here")
