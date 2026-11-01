"""Step 2b: keyword search, RRF fusion, reranking. The DB tests use rag_test."""

import pytest

from rag.db import init_schema
from rag.ingest.pipeline import ingest_documents
from rag.models import Chunk, Document, RetrievedChunk
from rag.retrieval import Retriever, rrf
from rag.store import ChunkStore

DOCS = [
    Document(
        "tutorial/handling-errors",
        "Handling Errors",
        "https://fastapi.tiangolo.com/tutorial/handling-errors/",
        "# Handling Errors { #handling-errors }\n\n"
        "Raise an HTTPException with status_code 404 when an item is not found.",
    ),
    Document(
        "tutorial/response-model",
        "Response Model",
        "https://fastapi.tiangolo.com/tutorial/response-model/",
        "# Response Model { #response-model }\n\n"
        "Use response_model_exclude_unset to skip default values in the response.",
    ),
    Document(
        "tutorial/cors",
        "CORS",
        "https://fastapi.tiangolo.com/tutorial/cors/",
        "# CORS { #cors }\n\nUse CORSMiddleware to allow cross origin requests from browsers.",
    ),
]


def chunk(name: str) -> RetrievedChunk:
    return RetrievedChunk(Chunk(name, 0, "h", f"https://x/{name}/#a", f"text {name}"), 0.5)


@pytest.fixture
def store(conn, embedder):
    s = ChunkStore(conn)
    ingest_documents(DOCS, s, embedder, chunk_size=1000, chunk_overlap=100)
    return s


# --- RRF: pure function, no DB ---


def test_rrf_matches_docstring_example():
    a, b, c, d = chunk("A"), chunk("B"), chunk("C"), chunk("D")
    fused = rrf([[a, b, c], [c, d, a]], k=60)
    assert [r.chunk.document_id for r in fused] == ["A", "C", "B", "D"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 63)


def test_rrf_counts_a_chunk_found_twice_once():
    a = chunk("A")
    assert len(rrf([[a], [a]])) == 1


# --- Keyword search: real Postgres full-text search ---


def test_keyword_search_finds_exact_code_name(store):
    found = store.keyword_search("What does response_model_exclude_unset do?", 3)
    assert found[0].chunk.document_id == "tutorial/response-model"


def test_keyword_search_matches_any_word_not_all(store):
    # "teapot" is in no chunk. With AND semantics nothing would come back.
    found = store.keyword_search("return 404 teapot", 3)
    assert found[0].chunk.document_id == "tutorial/handling-errors"


def test_keyword_search_with_only_stop_words_returns_nothing(store):
    assert store.keyword_search("how do I?", 3) == []


def test_init_schema_adds_keyword_column_to_an_existing_index(conn, embedder):
    """Ido's index was built before step 2b: the column must appear without re-ingest."""
    with conn.cursor() as cur:
        cur.execute("DROP INDEX chunks_tsv_gin")
        cur.execute("ALTER TABLE chunks DROP COLUMN tsv")  # the step-1 schema
    store = ChunkStore(conn)
    ingest_documents(DOCS, store, embedder, 1000, 100)
    init_schema(conn, embedder.dim)  # what the eval and the API do at startup
    assert store.keyword_search("CORSMiddleware", 1)[0].chunk.document_id == "tutorial/cors"


# --- Retriever modes ---


class WordOverlapReranker:
    """Fake cross-encoder: score = how many question words appear in the text."""

    def score(self, question, texts):
        words = set(question.lower().split())
        return [float(len(words & set(t.lower().split()))) for t in texts]


def test_hybrid_returns_each_chunk_once(store, embedder):
    results = Retriever(store, embedder, "hybrid", candidate_k=10).retrieve("404 error", 3)
    keys = [(r.chunk.document_id, r.chunk.index) for r in results]
    assert len(keys) == len(set(keys)) == 3


def test_rerank_reorders_by_reranker_score(store, embedder):
    retriever = Retriever(store, embedder, "rerank", WordOverlapReranker(), candidate_k=10)
    results = retriever.retrieve("allow cross origin requests from browsers", 3)
    assert results[0].chunk.document_id == "tutorial/cors"
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


def test_rerank_mode_requires_a_reranker(store, embedder):
    with pytest.raises(ValueError, match="needs a reranker"):
        Retriever(store, embedder, "hybrid_rerank")


def test_unknown_mode_is_rejected(store, embedder):
    with pytest.raises(ValueError, match="unknown retrieval mode"):
        Retriever(store, embedder, "magic")
