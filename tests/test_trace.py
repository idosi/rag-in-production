"""Tests for rag/trace.py: spans, the JSON line, and the current-trace helper."""

import json

import pytest

from rag.trace import Trace, span, tracing


class FakeClock:
    def __init__(self, now=100.0):
        self.now = now

    def __call__(self):
        return self.now


def test_every_trace_gets_its_own_request_id_and_a_given_one_is_kept():
    assert Trace().request_id != Trace().request_id
    assert Trace(request_id="abc-123").request_id == "abc-123"


def test_span_measures_ms_adds_up_and_is_recorded_when_the_block_raises():
    clock = FakeClock()
    t = Trace(clock=clock)
    with t.span("generate"):
        clock.now += 1.0
    with pytest.raises(RuntimeError):
        with t.span("generate"):
            clock.now += 0.5
            raise RuntimeError("Claude is down")
    assert t.spans["generate"] == pytest.approx(1500.0)


def test_to_json_is_one_line_with_spans_total_and_extra_fields():
    clock = FakeClock()
    t = Trace(request_id="r1", clock=clock)
    with t.span("retrieve"):
        clock.now += 0.0123456
    t.set(cache_hit=False, cost_usd=0.0042)
    clock.now += 0.1
    line = t.to_json()
    assert "\n" not in line
    data = json.loads(line)
    assert data["spans_ms"] == {"retrieve": 12.3}
    assert data["total_ms"] == pytest.approx(112.3, abs=0.1)
    assert data["cache_hit"] is False and data["cost_usd"] == 0.0042


def test_module_span_goes_to_the_current_trace_and_is_a_no_op_without_one():
    with span("nothing"):  # no current trace: must not fail
        pass
    clock = FakeClock()
    t = Trace(clock=clock)
    with tracing(t):
        with span("retrieve"):
            clock.now += 0.1
    assert t.spans["retrieve"] == pytest.approx(100.0)
    with span("after"):  # the trace is no longer current
        clock.now += 1
    assert "after" not in t.spans
