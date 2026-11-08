"""EXERCISE 3c-3: put the cache, the daily budget and the cost around the pipeline.

Run the tests:   uv run pytest exercises/guarded -q
They all fail now. Make them pass one by one, and commit after each green test.

This is the "wiring" step: you already wrote the parts (AnswerCache, SpendTracker).
Now one class uses them. It is a WRAPPER ("decorator pattern"): it has the same
method as RAGPipeline (`ask(question) -> Answer`), so the API can use it without
knowing it is there, and RAGPipeline itself stays unchanged.

THE FLOW OF ask(question)
    1. key = make_key(question, self.version)
    2. cache hit?   -> return a COPY of the cached answer, with
                       usage["cache_hit"] = True and usage["cost_usd"] = 0.0
    3. budget used up?  (self.spend.allow() is False) -> raise BudgetExceeded
    4. answer = self.inner.ask(question)         (the only step that costs money)
    5. cost = self.cost_fn(answer.usage); self.spend.record(cost)
    6. cache the answer, unless it is a "not found" answer (see below)
    7. return the answer with usage["cost_usd"] = cost and usage["cache_hit"] = False

THINK BEFORE YOU CODE
    - Why is the cache checked BEFORE the budget? (test 6)
    - Why must a hit return a copy and not edit the stored answer? (test 3)
      dataclasses.replace(answer, usage={...}) builds a modified copy.
    - What counts as "not found"? Look at NOT_FOUND in rag/generator.py and at
      what the pipeline returns when there are no sources (test 4).
    - If you cache the answer BEFORE adding cost_usd/cache_hit to its usage, what
      does a later hit see? Decide what you store.

cost_of(usage): dollars from tokens. The real prices are already in the repo:
    from rag.evals.answers import PRICES, cost_usd     <- you can just reuse cost_usd
Reusing it from an eval module is a smell (production code importing eval code).
In the final version we move PRICES + cost_usd to src/rag/cost.py; for now, import.

HINTS (open one at a time, only when stuck)
    1. __init__ only stores its arguments; the tests pass them by keyword.
    2. Get test 1 and 7 green first (a plain miss + cost_of), then the cache.
    3. usage can be empty (e.g. a fake generator). cost_fn handles that: cost_usd
       needs "input_tokens" and "output_tokens", so guard with `if usage`.
"""

from rag.models import Answer


class BudgetExceeded(Exception):
    """The daily spend limit is used up. The API turns this into HTTP 503."""


def cost_of(usage: dict) -> float:
    raise NotImplementedError


class GuardedPipeline:
    def __init__(self, inner, cache, spend, version: str, cost_fn=cost_of):
        raise NotImplementedError

    def ask(self, question: str) -> Answer:
        raise NotImplementedError
