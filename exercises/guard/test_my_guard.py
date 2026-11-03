"""Tests for exercise 2. Do not edit; make them pass by editing my_guard.py.

Read them in order: each one adds one idea.
"""

import hmac

import pytest
from fastapi import HTTPException

from exercises.guard.my_guard import Guard


class FakeLimiter:
    """Pretends to be the rate limiter. Records who was asked, answers what we say."""

    def __init__(self, wait=0.0):
        self.wait = wait
        self.asked = []

    def allow(self, caller):
        self.asked.append(caller)
        return self.wait


def status_of(guard, api_key=None, ip="1.1.1.1"):
    """Run check(); return the HTTP status it raised, or None if it let the request in."""
    try:
        guard.check(api_key, ip)
    except HTTPException as e:
        return e.status_code
    return None


def test_1_no_keys_and_no_limiter_lets_everything_in():
    assert status_of(Guard([], None)) is None


def test_2_missing_key_is_401():
    assert status_of(Guard(["secret"], None), api_key=None) == 401


def test_3_wrong_key_is_401():
    assert status_of(Guard(["secret"], None), api_key="nope") == 401


def test_4_any_configured_key_is_accepted():
    g = Guard(["key-a", "key-b"], None)
    assert status_of(g, api_key="key-a") is None
    assert status_of(g, api_key="key-b") is None


def test_5_rate_limit_exceeded_is_429_with_retry_after_rounded_up():
    g = Guard(["secret"], FakeLimiter(wait=12.3))
    with pytest.raises(HTTPException) as e:
        g.check("secret", "1.1.1.1")
    assert e.value.status_code == 429
    assert e.value.headers["Retry-After"] == "13"


def test_6_the_caller_is_the_key_when_auth_is_on_and_the_ip_when_it_is_off():
    with_auth = FakeLimiter()
    Guard(["secret"], with_auth).check("secret", "9.9.9.9")
    assert with_auth.asked == ["secret"]

    without_auth = FakeLimiter()
    Guard([], without_auth).check(None, "9.9.9.9")
    assert without_auth.asked == ["9.9.9.9"]


def test_7_a_bad_key_never_touches_the_limiter():
    limiter = FakeLimiter()
    assert status_of(Guard(["secret"], limiter), api_key="nope") == 401
    assert limiter.asked == []  # authentication happens first


def test_8_keys_are_compared_with_compare_digest(monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append(1)
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    g = Guard(["key-a", "key-b", "key-c"], None)
    assert status_of(g, api_key="key-a") is None
    assert len(calls) == 3  # it checked ALL keys, it did not stop at the first match
