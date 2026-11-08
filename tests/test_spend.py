"""Tests for rag/spend.py: daily dollar limit (Ido's exercise 3c-1 tests)."""

import pytest

from rag.spend import SpendTracker

DAY = 86_400  # seconds in a day


class FakeClock:
    """A clock we move by hand, so "tomorrow" takes no real time."""

    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def test_1_new_tracker_has_spent_nothing_and_allows():
    t = SpendTracker(daily_budget=1.00, clock=FakeClock())
    assert t.spent_today() == 0.0
    assert t.allow() is True


def test_2_record_adds_up():
    t = SpendTracker(daily_budget=1.00, clock=FakeClock())
    t.record(0.01)
    t.record(0.02)
    # Floats: 0.01 + 0.02 is 0.030000000000000002, so compare with approx.
    assert t.spent_today() == pytest.approx(0.03)


def test_3_under_budget_still_allows():
    t = SpendTracker(daily_budget=1.00, clock=FakeClock())
    t.record(0.99)
    assert t.allow() is True


def test_4_reaching_the_budget_blocks():
    t = SpendTracker(daily_budget=1.00, clock=FakeClock())
    t.record(0.60)
    t.record(0.40)  # exactly the budget: the next question would go over it
    assert t.allow() is False


def test_5_a_new_day_starts_from_zero():
    clock = FakeClock(now=10 * DAY + 100)  # 100 seconds after midnight (UTC)
    t = SpendTracker(daily_budget=1.00, clock=clock)
    t.record(1.00)
    assert t.allow() is False

    clock.now += DAY - 200  # still the same day (100 s before midnight)
    assert t.allow() is False

    clock.now += 200  # 100 s after the next midnight
    assert t.spent_today() == 0.0
    assert t.allow() is True


def test_6_negative_cost_is_a_bug():
    t = SpendTracker(daily_budget=1.00, clock=FakeClock())
    with pytest.raises(ValueError):
        t.record(-0.01)
