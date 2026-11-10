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


def test_ready_reports_chunk_count_and_shutdown_closes_the_connection(monkeypatch):
    pipeline = make_pipeline()
    monkeypatch.setattr(api, "build_pipeline", lambda: pipeline)
    with TestClient(api.app) as client:
        r = client.get("/ready")
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

    llm_model = "m"
    docs_version = "0"
    top_k = 5
    retrieval_mode = "vector"
    answer_cache_max_items = 10
    answer_cache_ttl_seconds = 60.0

    def __init__(self, keys=None, rate=20, budget=5.0):
        from pydantic import SecretStr

        self.daily_budget_usd = budget
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


def test_on_cloud_run_an_open_ask_refuses_to_start(monkeypatch):
    # Cloud Run sets K_SERVICE in every container (step 3d). Forgetting API_KEYS there
    # must fail the deploy, not publish a URL that spends money for anyone.
    monkeypatch.setenv("K_SERVICE", "rag-api")
    with pytest.raises(RuntimeError, match="API_KEYS"):
        with client_with(monkeypatch):
            pass
    with client_with(monkeypatch, keys="secret") as c:  # with keys it starts normally
        assert c.get("/health").status_code == 200


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


# ---------------------------------------------------------------- cost control (step 3c)


class OneAnswerGenerator:
    """A generator that answers (and reports tokens) so the money path is exercised."""

    def __init__(self):
        self.calls = 0

    def generate(self, question, sources):
        from rag.models import Answer

        self.calls += 1
        usage = {"model": "claude-haiku-5-5", "input_tokens": 1_000_000, "output_tokens": 0}
        return Answer(text="an answer [1]", sources=sources, cited=[1], usage=usage)


class OneChunkRetriever(FakeRetriever):
    def retrieve(self, question, k):
        from rag.models import Chunk, RetrievedChunk

        return [RetrievedChunk(Chunk("doc", 0, "Heading", "http://u", "text"), 0.9)]


def paid_pipeline(generator):
    return RAGPipeline(OneChunkRetriever(), generator, top_k=5)


def test_response_reports_cost_and_the_second_identical_question_is_a_free_cache_hit(monkeypatch):
    gen = OneAnswerGenerator()
    monkeypatch.setattr(api, "build_pipeline", lambda: paid_pipeline(gen))
    monkeypatch.setattr(api, "get_settings", lambda: FakeSettings())
    with TestClient(api.app) as c:
        first = c.post("/ask", json=ASK).json()
        second = c.post("/ask", json={"question": "  how do i do x "}).json()
    assert first["usage"]["cache_hit"] is False
    assert first["usage"]["cost_usd"] == pytest.approx(0.10)  # 1M haiku input tokens
    assert second["usage"]["cache_hit"] is True
    assert second["usage"]["cost_usd"] == 0.0
    assert gen.calls == 1


def test_over_the_daily_budget_is_503_but_cached_questions_still_work(monkeypatch):
    gen = OneAnswerGenerator()
    monkeypatch.setattr(api, "build_pipeline", lambda: paid_pipeline(gen))
    monkeypatch.setattr(api, "get_settings", lambda: FakeSettings(budget=0.10))
    with TestClient(api.app) as c:
        assert c.post("/ask", json=ASK).status_code == 200  # spends the whole 0.10
        assert c.post("/ask", json={"question": "A new question"}).status_code == 503
        assert c.post("/ask", json=ASK).status_code == 200  # cached: free, so still served
    assert gen.calls == 1


# ---------------------------------------------------------------- tracing (step 3c)


def test_every_answer_has_a_request_id_header_and_one_json_trace_line(monkeypatch):
    import json
    import logging

    lines = []

    class Grab(logging.Handler):
        def emit(self, record):
            lines.append(record.getMessage())

    handler = Grab()
    logging.getLogger("rag.trace").addHandler(handler)
    gen = OneAnswerGenerator()
    monkeypatch.setattr(api, "build_pipeline", lambda: paid_pipeline(gen))
    monkeypatch.setattr(api, "get_settings", lambda: FakeSettings())
    try:
        with TestClient(api.app) as c:
            r = c.post("/ask", json=ASK, headers={"X-Request-ID": "req-42"})
    finally:
        logging.getLogger("rag.trace").removeHandler(handler)

    assert r.headers["x-request-id"] == "req-42"  # the caller's id is kept
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["request_id"] == "req-42"
    assert set(data["spans_ms"]) == {"retrieve", "generate"}  # the pipeline's two steps
    assert data["cache_hit"] is False
    assert data["cost_usd"] == pytest.approx(0.10)
    assert data["status"] == 200
    assert "How do I do X" not in lines[0]  # the question text is never logged


def test_a_503_is_traced_too_and_a_generated_id_is_returned(monkeypatch):
    gen = OneAnswerGenerator()
    monkeypatch.setattr(api, "build_pipeline", lambda: paid_pipeline(gen))
    monkeypatch.setattr(api, "get_settings", lambda: FakeSettings(budget=0.10))
    with TestClient(api.app) as c:
        c.post("/ask", json=ASK)
        r = c.post("/ask", json={"question": "A new question"})
    assert r.status_code == 503
    assert len(r.headers["x-request-id"]) >= 8


def test_health_never_touches_the_database_but_ready_reports_it_down(monkeypatch):
    # Liveness vs readiness (step 3d): with the database down, /health must stay 200 (a
    # restart would not fix it) while /ready says 503 with a generic reason.
    pipeline = make_pipeline()

    def broken():
        raise RuntimeError('connection to "ep-secret-host", user "neondb_owner" failed')

    pipeline.retriever.store.count_chunks = broken
    monkeypatch.setattr(api, "build_pipeline", lambda: pipeline)
    with TestClient(api.app) as client:
        assert client.get("/health").status_code == 200
        r = client.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "not_ready", "reason": "database unreachable"}
    assert "neondb_owner" not in r.text  # the error text never reaches a public URL


def test_ready_is_503_when_the_index_is_empty(monkeypatch):
    pipeline = make_pipeline()
    pipeline.retriever.store.count_chunks = lambda: 0
    monkeypatch.setattr(api, "build_pipeline", lambda: pipeline)
    with TestClient(api.app) as client:
        r = client.get("/ready")
    assert r.status_code == 503
    assert "ingest" in r.json()["reason"]
