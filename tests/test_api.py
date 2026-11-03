"""The HTTP layer, with the real wiring shape but fake components (no model, no DB, no API key).

Why this file exists: /health and the shutdown hook once read `pipeline.store`, an
attribute that no longer existed after the retriever was introduced. Nothing tested
api.py, so the bug only showed up when the Docker container reported "unhealthy".
"""

import pytest
from fastapi.testclient import TestClient

import rag.api as api
from rag.generator import NOT_FOUND
from rag.pipeline import RAGPipeline
from rag.security import Guard, RateLimiter, parse_keys


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


# ---------------------------------------------------------------- security (step 3b)


class FakeSettings:
    """Only the fields the lifespan reads."""

    def __init__(self, keys=None, rate=20):
        from pydantic import SecretStr

        self.api_keys = SecretStr(keys) if keys else None
        self.rate_limit_per_minute = rate


def client_with(monkeypatch, keys=None, rate=20):
    monkeypatch.setattr(api, "build_pipeline", make_pipeline)
    monkeypatch.setattr(api, "get_settings", lambda: FakeSettings(keys, rate))
    return TestClient(api.app)


ASK = {"question": "How do I do X?"}


def test_without_keys_configured_ask_is_open(monkeypatch):
    with client_with(monkeypatch) as c:
        assert c.post("/ask", json=ASK).status_code == 200


def test_missing_or_wrong_key_is_401_and_the_right_key_passes(monkeypatch):
    with client_with(monkeypatch, keys="secret-a, secret-b") as c:
        assert c.post("/ask", json=ASK).status_code == 401
        assert c.post("/ask", json=ASK, headers={"X-API-Key": "nope"}).status_code == 401
        assert c.post("/ask", json=ASK, headers={"X-API-Key": "secret-a"}).status_code == 200
        assert c.post("/ask", json=ASK, headers={"X-API-Key": "secret-b"}).status_code == 200


def test_health_stays_open_even_when_auth_is_on(monkeypatch):
    with client_with(monkeypatch, keys="secret") as c:
        assert c.get("/health").status_code == 200  # load balancers have no key


def test_rate_limit_returns_429_with_retry_after(monkeypatch):
    with client_with(monkeypatch, keys="secret", rate=2) as c:
        h = {"X-API-Key": "secret"}
        assert c.post("/ask", json=ASK, headers=h).status_code == 200
        assert c.post("/ask", json=ASK, headers=h).status_code == 200
        r = c.post("/ask", json=ASK, headers=h)
        assert r.status_code == 429
        assert int(r.headers["retry-after"]) >= 1


def test_a_rejected_request_never_reaches_the_pipeline(monkeypatch):
    calls = []
    monkeypatch.setattr(api, "build_pipeline", make_pipeline)
    monkeypatch.setattr(api, "get_settings", lambda: FakeSettings("secret"))
    with TestClient(api.app) as c:
        c.app.state.pipeline.retriever.retrieve = lambda q, k: calls.append(q) or []
        c.post("/ask", json=ASK)  # no key
    assert calls == []  # 401 happened before any retrieval (and so before any LLM cost)


def test_limiter_is_per_caller_and_window_slides():
    now = [0.0]
    lim = RateLimiter(limit=2, window=60, clock=lambda: now[0])
    assert lim.allow("a") == 0 and lim.allow("a") == 0
    assert lim.allow("a") > 0  # third request inside the window
    assert lim.allow("b") == 0  # another caller has its own budget
    now[0] = 61
    assert lim.allow("a") == 0  # the old requests left the window


def test_parse_keys_and_guard_without_keys_uses_the_ip():
    assert parse_keys(" a, b ,,") == ["a", "b"]
    assert parse_keys(None) == []
    g = Guard([], RateLimiter(1))
    g.check(None, "1.2.3.4")
    with pytest.raises(Exception) as e:
        g.check(None, "1.2.3.4")
    assert e.value.status_code == 429
    g.check(None, "5.6.7.8")  # a different IP is a different caller
