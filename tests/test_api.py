"""The HTTP layer, with the real wiring shape but fake components (no model, no DB, no API key).

Why this file exists: /health and the shutdown hook once read `pipeline.store`, an
attribute that no longer existed after the retriever was introduced. Nothing tested
api.py, so the bug only showed up when the Docker container reported "unhealthy".
"""

from fastapi.testclient import TestClient

import rag.api as api
from rag.generator import NOT_FOUND
from rag.pipeline import RAGPipeline


class FakeConn:
    closed = False

    def close(self):
        self.closed = True


class FakeStore:
    def __init__(self):
        self.conn = FakeConn()

    def count_chunks(self):
        return 745


class FakeRetriever:
    """Same shape as the real Retriever: it owns the store."""

    def __init__(self):
        self.store = FakeStore()

    def retrieve(self, question, k):
        return []


class FakeGenerator:
    def generate(self, question, sources):
        raise AssertionError("not reached: no sources")


def make_pipeline():
    return RAGPipeline(FakeRetriever(), FakeGenerator(), top_k=5)


def test_health_reports_chunk_count_and_shutdown_closes_the_connection(monkeypatch):
    pipeline = make_pipeline()
    monkeypatch.setattr(api, "build_pipeline", lambda: pipeline)
    with TestClient(api.app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok", "chunks": 745}
    assert pipeline.retriever.store.conn.closed  # lifespan shutdown ran without error


def test_ask_on_empty_retrieval_returns_not_found(monkeypatch):
    monkeypatch.setattr(api, "build_pipeline", make_pipeline)
    with TestClient(api.app) as client:
        r = client.post("/ask", json={"question": "How do I do X?"})
    assert r.status_code == 200
    assert r.json()["answer"] == NOT_FOUND
