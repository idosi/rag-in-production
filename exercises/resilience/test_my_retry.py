"""Tests for exercise 4-1. Do not edit; make them pass by editing my_retry.py.

Run:   uv run pytest exercises/resilience/test_my_retry.py -q
"""

import pytest

from exercises.resilience.my_retry import (
    UpstreamError,
    backoff_delay,
    call_with_retries,
    is_retryable,
    worst_case_seconds,
)

# ---- Part 1: is_retryable ----


def test_1_no_response_is_retryable():
    assert is_retryable(None) is True  # timeout / connection dropped


def test_2_rate_limit_and_server_errors_are_retryable():
    for status in (408, 409, 429, 500, 502, 503, 504, 529):
        assert is_retryable(status) is True, status


def test_3_client_errors_are_not_retryable():
    for status in (200, 400, 401, 403, 404, 413, 422, 600):
        assert is_retryable(status) is False, status


# ---- Part 2: backoff_delay ----


def test_4_ceiling_doubles_each_attempt():
    almost_one = lambda: 0.999999  # noqa: E731
    assert backoff_delay(0, rand=almost_one) == pytest.approx(0.5, abs=1e-3)
    assert backoff_delay(1, rand=almost_one) == pytest.approx(1.0, abs=1e-3)
    assert backoff_delay(3, rand=almost_one) == pytest.approx(4.0, abs=1e-3)


def test_5_never_above_cap():
    assert backoff_delay(10, rand=lambda: 0.999999) == pytest.approx(8.0, abs=1e-3)
    assert backoff_delay(10, cap=2.0, rand=lambda: 0.999999) == pytest.approx(2.0, abs=1e-3)


def test_6_full_jitter_scales_the_whole_delay():
    assert backoff_delay(2, rand=lambda: 0.0) == 0.0
    assert backoff_delay(2, rand=lambda: 0.25) == pytest.approx(0.5)  # 0.25 * 2.0
    delays = {backoff_delay(2) for _ in range(50)}  # the real random
    assert len(delays) > 1 and all(0 <= d < 2.0 for d in delays)


# ---- Part 3: worst_case_seconds ----


def test_7_no_retries_is_just_the_timeout():
    assert worst_case_seconds(30, 0) == 30


def test_8_attempts_plus_growing_waits():
    assert worst_case_seconds(20, 1) == pytest.approx(40.5)  # 20 + 0.5 + 20
    assert worst_case_seconds(10, 2) == pytest.approx(31.5)  # 10 + 0.5 + 10 + 1 + 10
    assert worst_case_seconds(10, 5, cap=1.0) == pytest.approx(60 + 0.5 + 1 * 4)


# ---- Part 4: call_with_retries ----


class Flaky:
    """Fails with the given errors, in order, then returns "ok"."""

    def __init__(self, *errors):
        self.errors = list(errors)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def test_9_success_first_time_does_not_sleep():
    slept = []
    fn = Flaky()
    assert call_with_retries(fn, 3, sleep=slept.append) == "ok"
    assert fn.calls == 1 and slept == []


def test_10_retries_then_succeeds_with_backoff_waits():
    slept = []
    fn = Flaky(UpstreamError(529), UpstreamError(None))
    assert call_with_retries(fn, 3, sleep=slept.append, rand=lambda: 0.5) == "ok"
    assert fn.calls == 3
    assert slept == pytest.approx([0.25, 0.5])  # 0.5*0.5, then 0.5*1.0


def test_11_not_retryable_raises_at_once():
    slept = []
    fn = Flaky(UpstreamError(401))
    with pytest.raises(UpstreamError) as e:
        call_with_retries(fn, 3, sleep=slept.append)
    assert e.value.status == 401 and fn.calls == 1 and slept == []


def test_12_gives_up_after_max_retries_with_the_last_error():
    slept = []
    last = UpstreamError(503)
    fn = Flaky(UpstreamError(500), UpstreamError(502), last, UpstreamError(500))
    with pytest.raises(UpstreamError) as e:
        call_with_retries(fn, 2, sleep=slept.append, rand=lambda: 0.0)
    assert e.value is last
    assert fn.calls == 3 and len(slept) == 2  # no sleep after the final failure


def test_13_retry_after_from_the_server_wins_but_is_capped():
    slept = []
    fn = Flaky(UpstreamError(429, retry_after=3.0), UpstreamError(429, retry_after=120.0))
    assert call_with_retries(fn, 2, sleep=slept.append, rand=lambda: 0.5) == "ok"
    assert slept == [3.0, 8.0]


def test_14_other_exceptions_are_not_retried():
    fn = Flaky(KeyError("bug in our code"))
    with pytest.raises(KeyError):
        call_with_retries(fn, 3, sleep=lambda s: None)
    assert fn.calls == 1
