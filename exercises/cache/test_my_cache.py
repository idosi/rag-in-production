"""Tests for exercise 3c-2. Do not edit; make them pass by editing my_cache.py.

Run:   uv run pytest exercises/cache -q
Read them in order: each one adds one idea.
"""

from exercises.cache.my_cache import AnswerCache, make_key

V1 = "claude-sonnet-5-5|docs-0.162.0|k5|rerank"  # what the answer depended on
V2 = "claude-haiku-5-5|docs-0.162.0|k5|rerank"


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now


def test_1_empty_cache_is_a_miss():
    c = AnswerCache(max_items=10, ttl=60, clock=FakeClock())
    assert c.get("k") is None
    assert (c.hits, c.misses) == (0, 1)


def test_2_put_then_get_is_a_hit():
    c = AnswerCache(max_items=10, ttl=60, clock=FakeClock())
    c.put("k", "the answer")
    assert c.get("k") == "the answer"
    assert (c.hits, c.misses) == (1, 0)


def test_3_same_question_written_differently_gives_the_same_key():
    a = make_key("How do I make a query parameter optional?", V1)
    b = make_key("  how do I make a   QUERY parameter optional ", V1)
    assert a == b


def test_4_different_words_give_a_different_key():
    a = make_key("How do I make a query parameter optional?", V1)
    b = make_key("How do I make a query parameter required?", V1)
    assert a != b


def test_5_a_different_model_or_index_gives_a_different_key():
    # Same question, but the answer came from another model: it must not be reused.
    q = "How do I make a query parameter optional?"
    assert make_key(q, V1) != make_key(q, V2)


def test_6_entries_expire_after_ttl():
    clock = FakeClock()
    c = AnswerCache(max_items=10, ttl=60, clock=clock)
    c.put("k", "old answer")
    clock.now = 59
    assert c.get("k") == "old answer"
    clock.now = 60  # exactly ttl seconds after put: expired
    assert c.get("k") is None
    assert len(c) == 0  # an expired entry is removed, not just hidden


def test_7_when_full_the_least_recently_used_entry_goes():
    c = AnswerCache(max_items=2, ttl=60, clock=FakeClock())
    c.put("a", 1)
    c.put("b", 2)
    c.get("a")  # "a" was just used, so "b" is now the least recently used
    c.put("c", 3)  # over the limit: one entry must go
    assert len(c) == 2
    assert c.get("b") is None
    assert c.get("a") == 1
    assert c.get("c") == 3


def test_8_put_on_an_existing_key_replaces_it():
    c = AnswerCache(max_items=2, ttl=60, clock=FakeClock())
    c.put("a", 1)
    c.put("a", 2)
    assert len(c) == 1
    assert c.get("a") == 2
