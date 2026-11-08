"""EXERCISE 3c-4: tracing one question.

Run the tests:   uv run pytest exercises/trace -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    A user says "it was slow" or "it gave a weird answer". Without a trace you can
    only guess: was it the search (ms), the reranker (100s of ms), or Claude
    (seconds)? Was it cached? What did it cost? A trace is the answer to "what
    happened to THIS request", as one log line you can search by request_id.

    Real systems use OpenTelemetry (spans sent to Jaeger, Datadog, ...). The idea is
    identical to this: an id, named spans with durations, and attributes. You build
    the 40-line version so you can explain the big one.

THE SPEC
    Trace(request_id=None, clock=time.perf_counter)
        request_id  given -> keep it; None -> make a new unique one
        clock       function returning seconds (tests pass a fake one)
        .request_id
        .spans      dict: name -> total milliseconds
        .span(name) a context manager:   with trace.span("retrieve"): ...
                    measures the block, adds it to .spans[name], even if the block raises
        .set(**fields)   extra facts to log: trace.set(cache_hit=False, cost_usd=0.004)
        .total_ms()  milliseconds since the Trace was created
        .to_json()   ONE line of JSON: request_id, spans_ms, total_ms and the set() fields.
                     Durations rounded to 1 decimal.

HINTS (open one at a time, only when stuck)
    1. A request id: uuid.uuid4().hex[:12] is unique enough for logs.
    2. @contextlib.contextmanager turns a generator function into a context manager:
           @contextmanager
           def span(self, name):
               start = ...
               try:
                   yield          # the with-block runs here
               finally:
                   ...            # runs even when the block raised
    3. dict.get(name, 0.0) + elapsed handles "first time" and "again".
    4. json.dumps(dict) gives one line unless you pass indent=.
    5. Which clock? time.perf_counter is for measuring durations (monotonic, precise).
       time.time can jump when the system clock is corrected.

THINK ABOUT (we discuss after the tests are green)
    - What must NEVER go in this log line? (the question text? the API key? Why?)
    - Your server has 20 requests at once. Why does request_id matter more then?
    - Where would this be created, so that api.py, the guarded pipeline and the
      retriever all write to the SAME trace?
"""

from contextlib import contextmanager
import time
from collections.abc import Callable
from typing import Any
import uuid
import json


class Trace:
    def __init__(
        self, request_id: str | None = None, clock: Callable[[], float] = time.perf_counter
    ):
        self.request_id = request_id or uuid.uuid4().hex[:12]
        self.clock = clock
        self.start_time = clock()
        self.spans: dict[str, float] = {}
        self.fields: dict[str, Any] = {}

    @contextmanager
    def span(self, name: str):
        start = self.clock()
        try:
            yield
        finally:
            elapsed = (self.clock() - start) * 1000  # convert to milliseconds
            self.spans[name] = self.spans.get(name, 0.0) + elapsed 

    def set(self, **fields) -> None:
        self.fields.update(fields)

    def total_ms(self) -> float:
        return (self.clock() - self.start_time) * 1000

    def to_json(self) -> str:

        data = {
            "request_id": self.request_id,
            "spans_ms": {name: round(ms, 1) for name, ms in self.spans.items()},
            "total_ms": round(self.total_ms(), 1),
            **self.fields,
        }
        return json.dumps(data)
