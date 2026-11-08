"""Tracing one question: an id, how long each step took, and a few facts, as one log line.

Why: "it was slow" or "it answered strangely" is a guess without it. With the line you
see which step took the time (search: ms, reranker: 100s of ms, Claude: seconds), whether
the answer was cached and what it cost, and you find the line by request_id.
Real systems send the same things (id, named spans with durations, attributes) to
OpenTelemetry / Datadog; this is the 60-line version of that idea.

HOW IT IS USED
    api.py       creates a Trace per request, puts it in a ContextVar (below), and logs
                 trace.to_json() when the request ends
    pipeline.py  wraps its steps in `with span("retrieve"):` / `with span("generate"):`
                 and does not need to know whether anyone is tracing (no trace = no-op)

Trace itself was written by Ido as exercise 3c-4. The ContextVar part is new.
"""

import json
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any


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


# A ContextVar is a variable with one value per request/thread of work. 20 requests at
# once each see THEIR trace, and code deep inside the pipeline can reach it without
# passing it through every function signature.
_current: ContextVar[Trace | None] = ContextVar("current_trace", default=None)


@contextmanager
def tracing(trace: Trace) -> Iterator[Trace]:
    """Make `trace` the current one for the code inside the with-block."""
    token = _current.set(trace)
    try:
        yield trace
    finally:
        _current.reset(token)


@contextmanager
def span(name: str):
    """Time a step in the current trace. Does nothing when there is no current trace
    (CLI, evals, tests), so library code can always call it."""
    trace = _current.get()
    if trace is None:
        yield
    else:
        with trace.span(name):
            yield
