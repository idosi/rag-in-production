"""What /ready answers (step 3d). Written by Ido as exercise 3d-2.

TWO QUESTIONS, TWO ENDPOINTS
    GET /health   "is the process alive?"   never touches the DB, always 200. The platform
                  restarts the container when it fails, and restarting does not fix a database.
    GET /ready    "can it answer?"          this function: 200 only if the DB answers AND
                  the index is not empty, otherwise 503 with a generic reason.
"""

import logging
from collections.abc import Callable

log = logging.getLogger("rag.api")


def readiness(count_chunks: Callable[[], int]) -> tuple[int, dict]:
    try:
        n = count_chunks()
    except Exception as e:
        # The type is safe to log; the message can contain the host and user name.
        log.warning("readiness: database check failed: %s", type(e).__name__)
        return 503, {"status": "not_ready", "reason": "database unreachable"}
    if n > 0:
        return 200, {"status": "ok", "chunks": n}
    return 503, {"status": "not_ready", "reason": "index is empty: run ingest"}
