"""EXERCISE 3c-1: a daily spend limit (a "circuit breaker" for money).

Run the tests:   uv run pytest exercises/spend -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    The rate limiter (3b) caps requests per key per minute. It does not cap DOLLARS.
    A bug that loops, a leaked key, or one heavy user can still burn the budget,
    and you find out from the invoice. A daily cap turns "surprise bill" into
    "the service says 503 until midnight" + an alert.

THE SPEC
    SpendTracker(daily_budget, clock)
        daily_budget  dollars allowed per day (UTC), e.g. 1.00
        clock         function returning "now" in seconds since 1970 (tests pass a
                      fake one, real code passes time.time)

    .record(cost)   add the cost of one answer. Negative cost -> ValueError.
    .spent_today()  dollars spent since the last midnight (UTC)
    .allow()        True while spent_today() < daily_budget, else False

THE IDEA
    Keep two things: which day you are counting, and how much was spent in it.
    Before reading or adding, check if the day changed. If it did, start from 0.

HINTS (open one at a time, only when stuck)
    1. How do you turn "seconds since 1970" into "which day"?  int(seconds // 86400)
    2. Write one small helper, e.g. _roll(), that does the day check, and call it
       at the start of every public method.
    3. Do NOT call time.time() directly inside the methods; call self.clock().
    4. FastAPI runs requests in several threads (like the rate limiter). A
       threading.Lock around the read-modify-write keeps two answers from being
       counted as one. No test checks it, but the reviewer will.
"""

import time
from collections.abc import Callable


class SpendTracker:
    def __init__(self, daily_budget: float, clock: Callable[[], float] = time.time):
        self.daily_budget = daily_budget
        self.clock = clock
        # TODO: what state do you need?

    def record(self, cost: float) -> None:
        raise NotImplementedError

    def spent_today(self) -> float:
        raise NotImplementedError

    def allow(self) -> bool:
        raise NotImplementedError
