"""Tests for exercise 3c-4. Do not edit; make them pass by editing my_trace.py.

Run:   uv run pytest exercises/trace -q
"""

import json

import pytest

from exercises.trace.my_trace import Trace


class FakeClock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


def test_1_every_trace_gets_its_own_request_id():
    a, b = Trace(), Trace()
    assert a.request_id != b.request_id
    assert len(a.request_id) >= 8


def test_2_a_given_request_id_is_kept():
    # Behind a load balancer the id often arrives in a header (X-Request-ID).
    assert Trace(request_id="abc-123").request_id == "abc-123"


def test_3_span_measures_the_time_inside_the_with_block_in_ms():
    clock = FakeClock()
    t = Trace(clock=clock)
    with t.span("retrieve"):
        clock.now += 0.25  # 250 ms pass inside the block
    assert t.spans["retrieve"] == pytest.approx(250.0)


def test_4_the_same_span_name_twice_adds_up():
    clock = FakeClock()
    t = Trace(clock=clock)
    for _ in range(2):
        with t.span("generate"):
            clock.now += 1.0
    assert t.spans["generate"] == pytest.approx(2000.0)


def test_5_a_span_is_recorded_even_when_the_block_raises_and_the_error_goes_on():
    clock = FakeClock()
    t = Trace(clock=clock)
    with pytest.raises(RuntimeError):
        with t.span("generate"):
            clock.now += 0.5
            raise RuntimeError("Claude is down")
    assert t.spans["generate"] == pytest.approx(500.0)


def test_6_total_ms_is_the_time_since_the_trace_started():
    clock = FakeClock()
    t = Trace(clock=clock)
    clock.now += 2.0
    assert t.total_ms() == pytest.approx(2000.0)


def test_7_to_json_is_one_line_with_everything_needed_to_debug():
    clock = FakeClock()
    t = Trace(request_id="r1", clock=clock)
    with t.span("retrieve"):
        clock.now += 0.0123456
    t.set(cache_hit=False, cost_usd=0.0042, model="claude-sonnet-5-5")
    clock.now += 0.1

    line = t.to_json()
    assert "\n" not in line  # one line per question: easy to grep and to ship to a log tool
    data = json.loads(line)
    assert data["request_id"] == "r1"
    assert data["spans_ms"] == {"retrieve": 12.3}  # rounded to 1 decimal
    assert data["total_ms"] == pytest.approx(112.3, abs=0.1)
    assert data["cache_hit"] is False
    assert data["cost_usd"] == 0.0042
    assert data["model"] == "claude-sonnet-5-5"
