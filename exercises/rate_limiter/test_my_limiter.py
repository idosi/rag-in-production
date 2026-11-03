"""Tests for the exercise. Do not edit; make them pass by editing my_limiter.py.

Read them in order: each one adds one idea.
"""

from exercises.rate_limiter.my_limiter import RateLimiter


class FakeClock:
    """Time that moves only when we say so, so tests don't need sleep()."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make(limit=2, window=60):
    clock = FakeClock()
    return RateLimiter(limit, window, clock), clock


def test_1_requests_under_the_limit_are_allowed():
    lim, _ = make(limit=2)
    assert lim.allow("a") == 0.0
    assert lim.allow("a") == 0.0


def test_2_the_request_over_the_limit_is_rejected():
    lim, _ = make(limit=2)
    lim.allow("a")
    lim.allow("a")
    assert lim.allow("a") > 0  # rejected: returns how long to wait


def test_3_callers_have_separate_budgets():
    lim, _ = make(limit=1)
    assert lim.allow("a") == 0.0
    assert lim.allow("a") > 0
    assert lim.allow("b") == 0.0  # b is not affected by a


def test_4_old_requests_leave_the_window():
    lim, clock = make(limit=2, window=60)
    lim.allow("a")  # t=0
    lim.allow("a")  # t=0
    assert lim.allow("a") > 0
    clock.now = 61  # the two requests are now older than 60 seconds
    assert lim.allow("a") == 0.0


def test_5_wait_time_is_until_the_oldest_request_leaves():
    lim, clock = make(limit=2, window=60)
    lim.allow("a")  # t=0
    clock.now = 10
    lim.allow("a")  # t=10
    clock.now = 30
    # oldest is t=0, it leaves the window at t=60 -> 30 seconds from now
    assert lim.allow("a") == 30


def test_6_rejected_requests_are_not_counted():
    lim, clock = make(limit=1, window=60)
    lim.allow("a")  # t=0, allowed
    clock.now = 30
    assert lim.allow("a") > 0  # rejected at t=30, must NOT be remembered
    clock.now = 61  # the only counted request (t=0) has left
    assert lim.allow("a") == 0.0
