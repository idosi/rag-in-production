"""EXERCISE 3e-1 and 3e-2: read the trace lines, and decide when to wake someone up.

Run the tests:   uv run pytest exercises/monitor -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    Step 3c made the API write ONE JSON line per question (rag/trace.py), for example:
        {"request_id": "a3f9c1", "spans_ms": {"retrieve": 180.2, "generate": 2900.1},
         "total_ms": 3100.4, "question_chars": 41, "status": 200,
         "cache_hit": false, "cost_usd": 0.0071, "model": "claude-sonnet-5-5", "cited": 2}
    A line tells you what happened to ONE request. Monitoring answers a different question:
    "how is the SERVICE doing right now?". That means turning many lines into a few numbers
    (errors, latency, cost), and deciding which numbers are bad enough to alert on.
    Cloud Monitoring does exactly this with log-based metrics and alert policies; you write
    the 60-line version first, so you can explain what those policies compute.

    The three numbers are the classic RED set: Rate (how many), Errors (how many failed),
    Duration (how slow). We add one for LLM systems: Cost.

PART 1 (tests 1-8):  percentile() and summarize()

    percentile(values, p) -> float
        p is 0..100. NEAREST RANK: sort, then take the value at position ceil(p/100 * n)
        (counting from 1). An empty list gives 0.0.
        Example: percentile([10, 20, 30, 40], 50) == 20   (position ceil(0.5*4) = 2)
                 percentile([10, 20, 30, 40], 95) == 40   (position ceil(0.95*4) = 4)

    summarize(lines) -> dict      `lines` is any iterable of strings (log lines)
        A line counts as a REQUEST only if it is JSON, is a JSON object, and has "request_id".
        Everything else (uvicorn startup text, warnings, an empty line) is counted in "skipped".
        Returned keys:
            requests        number of request lines
            skipped         number of lines that were not request lines
            errors          requests with status >= 500 EXCEPT 503
            rejected        requests with status == 503 (the daily budget is used up: the
                            service protecting our money, not a bug)
            error_rate      errors / requests            (0.0 when there are no requests)
            cache_hit_rate  hits / requests that have a cache_hit field (rejected requests
                            have none; 0.0 when there are none)
            p50_ms, p95_ms  percentile of "total_ms" over the requests that have it
            cost_usd        sum of "cost_usd" (a missing one counts as 0)

PART 2 (tests 9-13):  check_alerts()

    check_alerts(summary, limits) -> list[str]
        `limits` is a dict with: min_requests, max_error_rate, max_p95_ms, max_cost_usd.
        Returns the NAMES of the alerts that fire, in this order: "error_rate", "latency_p95",
        "cost", "budget_rejections". Empty list = all quiet.
            error_rate         error_rate  > max_error_rate   (only if requests >= min_requests)
            latency_p95        p95_ms      > max_p95_ms       (only if requests >= min_requests)
            cost               cost_usd    > max_cost_usd     (always)
            budget_rejections  rejected    > 0                (always)

HINTS (open one at a time, only when stuck)
    1. json.loads raises json.JSONDecodeError on text that is not JSON. A valid JSON line can
       also be a list or a number: check isinstance(data, dict).
    2. math.ceil, and remember that positions count from 1 while list indexes from 0.
    3. Build lists first (all the total_ms values, all the cache_hit values), then compute.
       Do not divide before checking for zero.
    4. A request with no "status" field: decide what is sensible and say why in a comment.
    5. Part 2 is five if-statements. The interesting part is not the code, it is the
       questions below.

THINK ABOUT (we discuss after the tests are green)
    - Why min_requests? Two requests and one error is a 50% error rate. Should that page you
      at 3 a.m.? What happens to a rate-based alert at night, when nobody uses the service?
    - Why p95 and not the average? (Imagine 99 requests of 1 second and 1 of 100 seconds.)
    - Why is a 503 from the budget NOT an error, yet still gets its own alert?
    - The summary of the LAST 5 MINUTES and of the LAST 24 HOURS answer different questions.
      Which one do you alert on, and which one do you put on a dashboard?
"""


def percentile(values: list[float], p: float) -> float:
    raise NotImplementedError


def summarize(lines) -> dict:
    raise NotImplementedError


def check_alerts(summary: dict, limits: dict) -> list[str]:
    raise NotImplementedError
