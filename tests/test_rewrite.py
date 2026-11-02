"""Step 2e: query rewriting. Pure unit tests, no database and no API."""

from types import SimpleNamespace

import pytest

from rag.models import Chunk, RetrievedChunk
from rag.retrieval import Retriever
from rag.rewrite import ClaudeQueryRewriter, clean


def chunk(name: str) -> RetrievedChunk:
    return RetrievedChunk(Chunk(name, 0, "h", f"https://x/{name}/#a", f"text {name}"), 0.5)


class TextEmbedder:
    """embed_query returns the text itself, so the stub store can tell queries apart."""

    def embed_query(self, text):
        return text


class StubStore:
    """search(query, k) returns a canned list per query and records what was asked."""

    def __init__(self, by_query):
        self.by_query = by_query
        self.asked = []

    def search(self, query, k):
        self.asked.append(query)
        return self.by_query[query][:k]


class FixedRewriter:
    def __init__(self, queries):
        self.queries = queries

    def rewrite(self, question):
        return self.queries


A, B, C = chunk("A"), chunk("B"), chunk("C")


def ids(results):
    return [r.chunk.document_id for r in results]


def test_rewrite_mode_searches_the_question_and_every_rewrite():
    store = StubStore({"q": [A, B], "rw": [C, A]})
    retriever = Retriever(
        store, TextEmbedder(), "rewrite", candidate_k=10, rewriter=FixedRewriter(["rw"])
    )
    results = retriever.retrieve("q", 3)
    assert store.asked == ["q", "rw"]
    assert ids(results) == ["A", "C", "B"]  # A is in both lists, so it rises to the top


def test_rewrite_finds_what_the_plain_question_misses():
    store = StubStore({"q": [B], "rw": [A]})
    retriever = Retriever(
        store, TextEmbedder(), "rewrite", candidate_k=10, rewriter=FixedRewriter(["rw"])
    )
    assert "A" in ids(retriever.retrieve("q", 5))


def test_failed_rewriter_falls_back_to_the_plain_search():
    store = StubStore({"q": [A, B]})
    retriever = Retriever(
        store, TextEmbedder(), "rewrite", candidate_k=10, rewriter=FixedRewriter([])
    )
    assert ids(retriever.retrieve("q", 2)) == ["A", "B"]


def test_reranker_scores_against_the_original_question():
    seen = {}

    class SpyReranker:
        def score(self, question, texts):
            seen["question"] = question
            return [float(i) for i in range(len(texts))]

    store = StubStore({"q": [A], "rw": [B]})
    retriever = Retriever(
        store, TextEmbedder(), "rewrite_rerank", SpyReranker(), 10, rewriter=FixedRewriter(["rw"])
    )
    retriever.retrieve("q", 2)
    assert seen["question"] == "q"  # not the rewrite


def test_rewrite_mode_requires_a_rewriter():
    with pytest.raises(ValueError, match="needs a rewriter"):
        Retriever(StubStore({}), TextEmbedder(), "rewrite")


def test_clean_drops_empty_duplicate_and_the_question_itself_and_keeps_two():
    out = clean("How do I X?", ["how do i x?", "  ", "alpha", "ALPHA", "beta", "gamma"])
    assert out == ["alpha", "beta"]


class FakeMessages:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def parse(self, **kwargs):
        if self.error:
            raise self.error
        return self.result


def rewriter_with(messages):
    r = ClaudeQueryRewriter.__new__(ClaudeQueryRewriter)  # skip creating a real client
    r.model = "claude-haiku-5-5"
    r.client = SimpleNamespace(messages=messages)
    return r


def test_claude_rewriter_returns_cleaned_queries():
    parsed = SimpleNamespace(queries=["response_model exclude fields", "output model"])
    r = rewriter_with(FakeMessages(SimpleNamespace(parsed_output=parsed)))
    assert r.rewrite("q") == ["response_model exclude fields", "output model"]


def test_claude_rewriter_never_raises():
    assert rewriter_with(FakeMessages(error=RuntimeError("429"))).rewrite("q") == []
    assert rewriter_with(FakeMessages(SimpleNamespace(parsed_output=None))).rewrite("q") == []
