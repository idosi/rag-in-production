"""EXERCISE 3c-2: an answer cache (exact match, TTL + LRU).

Run the tests:   uv run pytest exercises/cache -q
They all fail now. Make them pass one by one, and commit after each green test.

WHY
    Each answer costs money (Claude) and 2-5 seconds. People ask the same
    questions again and again ("how do I install FastAPI?"). If we already
    answered it, with the same model and the same index, return the saved answer:
    0 dollars and about 1 ms.

THE SPEC
    make_key(question, version) -> str
        The same question written differently ("How do I X?" / "  how do i  x ")
        must give the same key. `version` is everything the answer depends on
        (model, docs version, top_k, retrieval mode), so a change to any of them
        gives a new key and the old answer is never reused.

    AnswerCache(max_items, ttl, clock)
        .get(key) -> value or None    counts self.hits / self.misses
        .put(key, value)
        len(cache)                    number of entries stored
        - An entry older than `ttl` seconds is expired: get() removes it, returns None.
        - When there are more than `max_items` entries, remove the one that was
          used (get or put) least recently. That is "LRU": least recently used.

HINTS (open one at a time, only when stuck)
    1. Normalising: lower(), split() and " ".join(...) collapse spaces;
       rstrip("?.!") drops the end punctuation. Then join it with `version`.
    2. What do you store per key? The value AND the time it was stored.
    3. collections.OrderedDict remembers insertion order, and has
       move_to_end(key) (mark as just used) and popitem(last=False) (remove the
       oldest). That is exactly LRU.
    4. __len__(self) is what len(cache) calls.
    5. Lock again: several threads call get/put at once (see SpendTracker).

THINK ABOUT (we discuss after the tests are green, no code needed)
    - Why not a "semantic cache" (similar questions by embedding)? Hint:
      "make the parameter optional" vs "make the parameter required".
    - Should we cache a refusal or a "not found" answer? A failed LLM call?
    - The API runs several containers (Cloud Run). Each has its own memory. What
      does that do to the hit rate, and what would you use instead?
"""

import time
from collections.abc import Callable


def make_key(question: str, version: str) -> str:
    raise NotImplementedError


class AnswerCache:
    def __init__(self, max_items: int, ttl: float, clock: Callable[[], float] = time.monotonic):
        self.max_items = max_items
        self.ttl = ttl
        self.clock = clock
        self.hits = 0
        self.misses = 0
        # TODO: where do the entries live?

    def get(self, key: str):
        raise NotImplementedError

    def put(self, key: str, value) -> None:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError
