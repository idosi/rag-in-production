"""Answer cache: the same question (same model, same index) is answered once.

Sits in guarded.py, in front of the pipeline. A hit costs 0 dollars and about 1 ms
instead of 2-5 seconds and a Claude call. Exact match only, on purpose: a semantic
cache would treat "make the parameter optional" and "make it required" as the same
question (docs/learning/03c). Entries expire after `ttl` seconds and, when full, the
least recently used one goes. Lives in this process' memory: with N containers the
same question is answered N times (a shared Redis would fix that).

Written by Ido as exercise 3c-2, moved here unchanged.
"""

import collections
import threading
import time
from collections.abc import Callable
from typing import Any


def make_key(question: str, version: str) -> str:
    """Normalise the question and join it with the version to make a key."""
    normalised = " ".join(question.lower().split()).rstrip("?.!").strip()
    return f"{normalised} | {version}"


class AnswerCache:
    def __init__(self, max_items: int, ttl: float, clock: Callable[[], float] = time.monotonic):
        self.max_items = max_items
        self.ttl = ttl
        self.clock = clock
        self.hits = 0
        self.misses = 0
        self.cache = collections.OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            entry = self.cache.get(key, None)
            if entry is not None and self.clock() - entry[1] >= self.ttl:
                entry = None
                del self.cache[key]  # remove expired entry
            if entry is None:
                self.misses += 1
                return None
            else:
                self.cache.move_to_end(key)  # mark as recently used
                self.hits += 1
        return entry[0]

    def put(self, key: str, value) -> None:
        with self._lock:
            self.cache[key] = (value, self.clock())
            self.cache.move_to_end(key)
            while len(self.cache) > self.max_items:
                self.cache.popitem(last=False)  # remove least recently used

    def __len__(self) -> int:
        return len(self.cache)
