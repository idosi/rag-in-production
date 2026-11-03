"""Who may call the API, and how often. Two small, separate guards.

WHY THIS EXISTS
    POST /ask runs a paid LLM call. An API that anyone on the internet can call is
    an open wallet: a script in a loop can burn money in minutes. Two defences:

    1. AUTHENTICATION  "who are you?"      -> an API key in the X-API-Key header
    2. RATE LIMITING   "how often?"        -> at most N requests per minute per caller

    Both are checked BEFORE the pipeline runs, so a rejected request costs nothing.

HOW IT PLUGS IN
    api.py builds one `Guard` at startup and calls `guard.check(...)` from a FastAPI
    dependency on /ask. /health stays open: load balancers must be able to call it
    without a key.

HTTP STATUS CODES (a classic interview question)
    401 Unauthorized     no key, or a wrong one   ("I don't know who you are")
    429 Too Many Requests rate limit exceeded     (+ Retry-After: seconds to wait)
"""

import hmac
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException


def parse_keys(raw: str | None) -> list[str]:
    """'key1, key2' -> ['key1', 'key2']. Several keys allow rotation without downtime:
    add the new key, move clients over, then remove the old one."""
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


class RateLimiter:
    """Sliding window: at most `limit` requests in any `window` seconds, per caller.

    For each caller we remember the timestamps of their recent requests. A new
    request first forgets timestamps older than the window, then is allowed only if
    fewer than `limit` remain.

        limit=3, window=60:   t=0 ok   t=10 ok   t=20 ok   t=30 REJECTED
                              t=61 ok  (the t=0 request has left the window)

    LIMITATION (say this in interviews): the counters live in THIS process's memory.
    With 3 Cloud Run instances a caller gets 3x the limit, and a restart resets
    everything. It protects the wallet from a single noisy client; a strict global
    limit needs a shared store (Redis) or a gateway in front of the service.
    """

    def __init__(
        self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ):
        self.limit = limit
        self.window = window
        self.clock = clock  # injectable, so tests can move time without sleeping
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()  # FastAPI runs sync endpoints in several threads

    def allow(self, caller: str) -> float:
        """Return 0.0 if the request is allowed, else the seconds until it would be."""
        now = self.clock()
        with self._lock:
            hits = self._hits.setdefault(caller, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window - (now - hits[0])
            hits.append(now)
            return 0.0


class Guard:
    """Authentication + rate limiting, in that order."""

    def __init__(self, keys: list[str], limiter: RateLimiter | None):
        self.keys = keys
        self.limiter = limiter

    @property
    def auth_enabled(self) -> bool:
        return bool(self.keys)

    def check(self, api_key: str | None, client_ip: str) -> None:
        """Raise HTTPException (401 or 429) if the request must not run."""
        if self.keys:
            if not api_key or not self._valid(api_key):
                raise HTTPException(status_code=401, detail="Missing or invalid API key")
            caller = api_key  # a key identifies the client better than an IP does
        else:
            caller = client_ip  # auth is off (local development): fall back to the IP

        if self.limiter:
            wait = self.limiter.allow(caller)
            if wait > 0:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(int(wait) + 1)},
                )

    def _valid(self, api_key: str) -> bool:
        # compare_digest takes the same time whether the first character or the last
        # differs. With a plain `==` the response time could leak how many leading
        # characters of a guess were right (a "timing attack"). We check every key
        # without stopping early, for the same reason.
        ok = False
        for key in self.keys:
            ok |= hmac.compare_digest(api_key.encode(), key.encode())
        return ok
