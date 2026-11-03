"""EXERCISE: write a sliding-window rate limiter yourself.

Run the tests:   uv run pytest exercises/rate_limiter -q
They all fail now. Your job: make them pass, one by one.

THE SPEC
    RateLimiter(limit, window, clock)
        limit   how many requests a caller may make inside the window
        window  window length in seconds
        clock   a function that returns "now" in seconds (tests pass a fake one,
                real code passes time.monotonic)

    .allow(caller) -> float
        returns 0.0           if this request is allowed (and counts it)
        returns seconds > 0   if it is NOT allowed: how long until it would be

    Each caller has their own budget. A request is counted only if allowed.

THE IDEA (sliding window)
    For every caller, remember the times of their recent allowed requests.
    On a new request:
      1. forget times that are older than the window
      2. if `limit` times remain -> reject, and say how long until the oldest one
         leaves the window
      3. otherwise remember "now" and allow

HINTS (open one at a time, only when stuck)
    - What data structure holds "the times for each caller"?  dict: caller -> list
    - The oldest time is at the front. collections.deque makes removing from the
      front cheap (popleft), a list does not. A list is fine for this exercise.
    - Do NOT use time.time() / time.monotonic() directly; call self.clock().
"""

import threading
import time
from collections import deque
from collections.abc import Callable



class RateLimiter:
    def __init__(
        self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ):
        self.limit = limit
        self.window = window
        self.clock = clock
        self.hits = {}  # Dictionary to store caller -> list of request times
        self._lock = threading.Lock()  # FastAPI runs sync endpoints in several threads


    def allow(self, caller: str) -> float:
        now = self.clock()
        with self._lock:
            hits = self.hits.setdefault(caller, deque())
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window - (now - hits[0])
            hits.append(now)
        return 0.0
