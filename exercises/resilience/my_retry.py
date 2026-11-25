"""EXERCISE 4-1: retry with backoff, and the time budget it must fit in.

Run the tests:   uv run pytest exercises/resilience/test_my_retry.py -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    Every call to Claude crosses the internet to a service shared with everyone else.
    Sometimes it is slow, overloaded (529), rate limited (429), or the connection drops.
    Most of these failures are SHORT: the same request a second later works.
    So production code retries, but carefully:
      - only errors that a retry can fix (retryable), never a bad request (400) or a bad key (401)
      - waiting longer each time (exponential backoff), so a struggling server gets air
      - with RANDOM jitter, so 1,000 clients that failed together do not retry together
      - within a total time budget: Cloud Run cuts our request at 60 s (Makefile: --timeout 60)

    IMPORTANT: the anthropic SDK already does all of this (2 retries by default). In the real
    code (generator.py) we only CONFIGURE it. You write the mechanism here so you can explain
    what the SDK does, and why stacking your own retry loop on top of it is a bug.

PART 1 (tests 1-3):  is_retryable(status) -> bool
    status is the HTTP status code, or None when there was no response at all
    (connection refused, connection dropped, timeout).
        retryable:      None, 408 (request timeout), 409 (conflict), 429 (rate limit), any 5xx
                        (529 = Anthropic "overloaded" is a 5xx too)
        NOT retryable:  everything else, e.g. 400, 401, 403, 404, 413, 422

PART 2 (tests 4-6):  backoff_delay(attempt, base=0.5, cap=8.0, rand=random.random) -> float
    attempt counts retries from 0. "FULL JITTER" (the AWS architecture blog version):
        ceiling = min(cap, base * 2 ** attempt)
        delay   = rand() * ceiling          (rand() returns a float in [0, 1))
    attempt 0 -> up to 0.5 s, 1 -> up to 1 s, 2 -> up to 2 s, ... never above cap.

PART 3 (tests 7-8):  worst_case_seconds(timeout, max_retries, base=0.5, cap=8.0) -> float
    The LONGEST a call can take: every attempt runs until its timeout, and every wait is
    at its ceiling. 1 first try + max_retries retries, and one wait before each retry.
        worst_case_seconds(20, 1) == 20 + 0.5 + 20 == 40.5

PART 4 (tests 9-14):  call_with_retries(fn, max_retries, sleep=time.sleep, rand=random.random)
    Call fn() and return its result. If it raises an UpstreamError (defined below):
      - not retryable               -> raise it at once (do not sleep)
      - retryable, retries left     -> sleep, then call fn() again
      - retryable, no retries left  -> raise the LAST error
    How long to sleep before retry number `attempt` (0, 1, ...):
      - if the error has retry_after (the server said "Retry-After: 3"), sleep that,
        but never more than cap (8.0); a server can not make us wait a minute
      - otherwise backoff_delay(attempt, rand=rand)
    Any other exception (a bug in our code, KeyError, ...) is not caught at all.
    `sleep` and `rand` are parameters so the tests run instantly and know the numbers.

HINTS (open one at a time, only when stuck)
    1. Part 1 is one line. 500 <= status <= 599 is valid Python.
    2. Part 3: how many attempts? how many waits between them? The waits are not all the same.
    3. Part 4: a for loop over range(max_retries + 1) with try/except inside. Where is the
       last attempt different from the others?
    4. Part 4: write the "how long to sleep" rule as a small helper first.

THINK ABOUT (we discuss after the tests are green)
    - The SDK retries 2 times. If generator.py ALSO wrapped the call in call_with_retries(2),
      how many requests can ONE question send to Anthropic? (This is "retry amplification".)
    - Why is it safe to retry this call? Would it be safe to retry "charge the credit card"?
      (Look up "idempotent".)
    - Cloud Run gives us 60 s in total. Pick timeout and max_retries so worst_case_seconds
      plus ~2 s of retrieval fits. What do you give up if the timeout is too short?
    - Why does jitter help the SERVER more than it helps us?
"""

import random
import time
from collections.abc import Callable


class UpstreamError(Exception):
    """A failed call to another service. status None = no response (timeout, connection)."""

    def __init__(self, status: int | None, retry_after: float | None = None):
        super().__init__(f"upstream failed: status={status}")
        self.status = status
        self.retry_after = retry_after


def is_retryable(status: int | None) -> bool:
    raise NotImplementedError  # PART 1


def backoff_delay(
    attempt: int, base: float = 0.5, cap: float = 8.0, rand: Callable[[], float] = random.random
) -> float:
    raise NotImplementedError  # PART 2


def worst_case_seconds(
    timeout: float, max_retries: int, base: float = 0.5, cap: float = 8.0
) -> float:
    raise NotImplementedError  # PART 3


def call_with_retries(
    fn: Callable[[], object],
    max_retries: int,
    sleep: Callable[[float], None] = time.sleep,
    rand: Callable[[], float] = random.random,
):
    raise NotImplementedError  # PART 4
