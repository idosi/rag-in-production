"""End-to-end: ingest into a real Postgres, then ask. LLM is faked."""

from rag.generator import NOT_FOUND
from rag.ingest.pipeline import ingest_documents
from rag.models import Answer, Document
from rag.pipeline import RAGPipeline
from rag.retrieval import Retriever
from rag.store import ChunkStore

DOCS = [
    Document(
        "tutorial/cors",
        "CORS",
        "https://fastapi.tiangolo.com/tutorial/cors/",
        "# CORS { #cors }\n\nUse CORSMiddleware to allow cross origin requests from browsers.",
    ),
    Document(
        "tutorial/background-tasks",
        "Background Tasks",
        "https://fastapi.tiangolo.com/tutorial/background-tasks/",
        "# Background Tasks { #background-tasks }\n\n"
        "Run work after returning a response with BackgroundTasks.",
    ),
]


class EchoGenerator:
    def generate(self, question, sources):
        return Answer(text=f"top: {sources[0].chunk.document_id} [1]", sources=sources, cited=[1])


def test_ingest_then_retrieve(conn, embedder):
    store = ChunkStore(conn)
    stats = ingest_documents(DOCS, store, embedder, chunk_size=1000, chunk_overlap=100)
    assert stats == {"documents": 2, "skipped": 0, "chunks": 2, "deleted": 0}

    pipeline = RAGPipeline(Retriever(store, embedder), EchoGenerator(), top_k=2)
    answer = pipeline.ask("How do I allow cross origin requests?")
    assert answer.sources[0].chunk.document_id == "tutorial/cors"
    assert answer.sources[0].score > answer.sources[1].score


def test_reingest_is_idempotent(conn, embedder):
    store = ChunkStore(conn)
    ingest_documents(DOCS, store, embedder, 1000, 100)
    again = ingest_documents(DOCS, store, embedder, 1000, 100)
    assert again == {"documents": 0, "skipped": 2, "chunks": 0, "deleted": 0}
    assert store.count_chunks() == 2


def test_changed_document_replaces_old_chunks(conn, embedder):
    store = ChunkStore(conn)
    ingest_documents(DOCS, store, embedder, 1000, 100)
    edited = Document(DOCS[0].id, DOCS[0].title, DOCS[0].url, DOCS[0].text + "\n\nNew paragraph.")
    stats = ingest_documents([edited, DOCS[1]], store, embedder, 1000, 100)
    assert stats["documents"] == 1
    assert store.count_chunks() == 2  # replaced, not duplicated


def test_empty_index_skips_llm(conn, embedder):
    pipeline = RAGPipeline(Retriever(ChunkStore(conn), embedder), EchoGenerator(), top_k=3)
    assert pipeline.ask("anything").text == NOT_FOUND


def test_changing_ingestion_settings_reingests(conn, embedder):
    ingest_documents(DOCS, ChunkStore(conn, "1200:200:model-a"), embedder, 1000, 100)
    stats = ingest_documents(DOCS, ChunkStore(conn, "400:50:model-a"), embedder, 1000, 100)
    assert stats["documents"] == 2  # new settings: nothing is "unchanged"


def test_document_removed_from_source_is_deleted(conn, embedder):
    store = ChunkStore(conn)
    ingest_documents(DOCS, store, embedder, 1000, 100)
    stats = ingest_documents(DOCS[:1], store, embedder, 1000, 100)
    assert stats["deleted"] == 1
    assert store.count_chunks() == 1
    pipeline = RAGPipeline(Retriever(store, embedder), EchoGenerator(), top_k=5)
    found = pipeline.ask("background tasks")
    assert all(s.chunk.document_id != "tutorial/background-tasks" for s in found.sources)


def test_empty_load_does_not_wipe_index(conn, embedder):
    store = ChunkStore(conn)
    ingest_documents(DOCS, store, embedder, 1000, 100)
    assert ingest_documents([], store, embedder, 1000, 100)["deleted"] == 0
    assert store.count_chunks() == 2


def test_ingested_rows_are_committed(conn, embedder, test_database):
    """Regression: a write must be visible from a NEW connection.

    Every other test reads back on the same connection, which also sees
    uncommitted rows. That hid a bug where ingestion never committed: the CLI
    printed "661 chunks in total", then the process exited and Postgres rolled
    everything back.
    """
    from rag.db import connect

    ingest_documents(DOCS, ChunkStore(conn), embedder, 1000, 100)
    other = connect(test_database)
    try:
        assert ChunkStore(other).count_chunks() == 2
    finally:
        other.close()
