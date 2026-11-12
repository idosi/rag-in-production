"""Tests for exercises 3e-1 and 3e-2. Do not edit; make them pass by editing my_monitor.py.

Run:   uv run pytest exercises/monitor -q
"""

import json

import pytest

from exercises.monitor.my_monitor import check_alerts, percentile, summarize


def line(**fields) -> str:
    """One trace line, like the API writes it. Only what a test cares about is passed in."""
    base = {"request_id": "r1", "total_ms": 1000.0, "status": 200,
            "cache_hit": False, "cost_usd": 0.01}
    return json.dumps({**base, **fields})


# ---- Part 1: percentile ----


def test_1_percentile_nearest_rank():
    assert percentile([10, 20, 30, 40], 50) == 20
    assert percentile([10, 20, 30, 40], 95) == 40
    assert percentile([10, 20, 30, 40], 25) == 10


def test_2_percentile_does_not_need_sorted_input_and_does_not_change_it():
    values = [40, 10, 30, 20]
    assert percentile(values, 50) == 20
    assert values == [40, 10, 30, 20]  # the caller's list is left alone


def test_3_percentile_edges():
    assert percentile([], 95) == 0.0
    assert percentile([7], 50) == 7
    assert percentile([7], 99) == 7
    assert percentile(list(range(1, 101)), 95) == 95  # 100 values: the 95th is 95


# ---- Part 1: summarize ----


def test_4_counts_requests_and_skips_everything_that_is_not_a_request_line():
    lines = [
        line(request_id="a"),
        "INFO:     Started server process [1]",
        "",
        "[1, 2, 3]",  # valid JSON, but not an object
        '{"message": "no request id"}',  # an object, but not a request
        line(request_id="b"),
    ]
    s = summarize(lines)
    assert s["requests"] == 2
    assert s["skipped"] == 4


def test_5_errors_are_5xx_but_the_budget_503_is_counted_apart():
    s = summarize([
        line(status=200), line(status=200), line(status=500),
        line(status=503, cache_hit=None, cost_usd=None), line(status=422),
    ])
    assert s["requests"] == 5
    assert s["errors"] == 1  # only the 500: a 422 is the caller's mistake, a 503 is the budget
    assert s["rejected"] == 1
    assert s["error_rate"] == pytest.approx(0.2)


def test_6_cache_hit_rate_ignores_requests_that_have_no_cache_field():
    s = summarize([
        line(cache_hit=True), line(cache_hit=False), line(cache_hit=False),
        line(cache_hit=True),
        line(status=503, cache_hit=None),  # rejected before the cache answer: no information
        '{"request_id": "x", "status": 500}',  # crashed: no cache_hit key at all
    ])
    assert s["cache_hit_rate"] == pytest.approx(0.5)  # 2 hits out of 4 that know


def test_7_latency_percentiles_and_cost():
    lines = [line(total_ms=float(ms), cost_usd=0.5) for ms in range(100, 2100, 100)]  # 20 values
    lines.append('{"request_id": "no-total", "status": 500}')  # no total_ms, no cost
    s = summarize(lines)
    assert s["requests"] == 21
    assert s["p50_ms"] == 1000.0  # 10th of 20 values
    assert s["p95_ms"] == 1900.0  # 19th of 20 values
    assert s["cost_usd"] == pytest.approx(10.0)


def test_8_no_requests_gives_zeros_not_an_exception():
    s = summarize(["INFO: nothing here", ""])
    assert s["requests"] == 0
    assert s["skipped"] == 2
    assert s["error_rate"] == 0.0
    assert s["cache_hit_rate"] == 0.0
    assert s["p95_ms"] == 0.0
    assert s["cost_usd"] == 0.0


# ---- Part 2: check_alerts ----

LIMITS = {"min_requests": 20, "max_error_rate": 0.05, "max_p95_ms": 8000.0, "max_cost_usd": 1.0}


def summary(**over) -> dict:
    quiet = {"requests": 100, "skipped": 0, "errors": 0, "rejected": 0, "error_rate": 0.0,
             "cache_hit_rate": 0.3, "p50_ms": 2000.0, "p95_ms": 5000.0, "cost_usd": 0.4}
    return {**quiet, **over}


def test_9_all_quiet():
    assert check_alerts(summary(), LIMITS) == []


def test_10_error_rate_and_latency_fire_above_their_limits_only():
    assert check_alerts(summary(error_rate=0.10), LIMITS) == ["error_rate"]
    assert check_alerts(summary(error_rate=0.05), LIMITS) == []  # exactly at the limit: quiet
    assert check_alerts(summary(p95_ms=9000.0), LIMITS) == ["latency_p95"]


def test_11_rates_are_ignored_on_a_small_sample():
    # 2 requests, 1 error: 50%, but nobody should be woken up by two requests.
    small = summary(requests=2, errors=1, error_rate=0.5, p95_ms=30000.0)
    assert check_alerts(small, LIMITS) == []
    assert check_alerts({**small, "requests": 20}, LIMITS) == ["error_rate", "latency_p95"]


def test_12_cost_and_budget_rejections_fire_even_on_a_small_sample():
    s = summary(requests=1, cost_usd=1.5, rejected=1)
    assert check_alerts(s, LIMITS) == ["cost", "budget_rejections"]


def test_13_several_alerts_come_in_a_fixed_order():
    s = summary(error_rate=0.2, p95_ms=9000.0, cost_usd=2.0, rejected=3)
    assert check_alerts(s, LIMITS) == ["error_rate", "latency_p95", "cost", "budget_rejections"]
