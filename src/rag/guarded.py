"""Cache, daily budget and cost, wrapped around the pipeline.

Same method as RAGPipeline (`ask(question) -> Answer`), so api.py uses it without
knowing the difference, and pipeline.py stays untouched (decorator pattern).

ONE QUESTION, IN ORDER
    1. cache hit?   -> return a copy marked cache_hit=True, cost_usd=0 (free)
    2. budget used up? -> raise BudgetExceeded (api.py answers 503)
    3. inner.ask(question)         <- the only step that costs money
    4. add the cost to today's spend, put the answer in the cache
       (not "not found" answers: that could be a temporary retrieval miss)
    5. return a copy with cache_hit=False and cost_usd

The cache is checked BEFORE the budget on purpose: a hit costs nothing, so it is
still served after the budget is gone. The cache key contains everything the answer
depends on (model, docs version, top_k, retrieval mode): change any and old answers
are not reused.

Written by Ido as exercise 3c-3, moved here with imports updated.
"""

import dataclasses

from rag.cache import make_key
from rag.cost import cost_of
from rag.generator import NOT_FOUND
from rag.models import Answer


class BudgetExceeded(Exception):
    """The daily spend limit is used up. The API turns this into HTTP 503."""


class GuardedPipeline:
    def __init__(self, inner, cache, spend, version: str, cost_fn=cost_of):
        self.inner = inner
        self.cache = cache
        self.spend = spend
        self.version = version
        self.cost_fn = cost_fn

    def ask(self, question: str) -> Answer:
        key = make_key(question, self.version)
        cached_answer = self.cache.get(key)
        if cached_answer is not None:
            # Return a copy of the cached answer with updated usage
            return dataclasses.replace(
                cached_answer, usage={**cached_answer.usage, "cache_hit": True, "cost_usd": 0.0}
            )
        if not self.spend.allow():
            raise BudgetExceeded("Daily spend limit exceeded.")
        answer = self.inner.ask(question)
        cost = self.cost_fn(answer.usage)
        self.spend.record(cost)
        result = dataclasses.replace(
            answer, usage={**answer.usage, "cache_hit": False, "cost_usd": cost}
        )
        if answer.text != NOT_FOUND and answer.sources:
            self.cache.put(key, answer)
        return result
