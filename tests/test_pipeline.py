"""End-to-end: ingest into a real Postgres, then ask. LLM is faked."""

from rag.generator import NOT_FOUND
from rag.ingest.pipeline import ingest_documents
from rag.models import Answer, Document
from rag.pipeline import RAGPipeline
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
    assert stats == {"documents": 2, "skipped": 0, "chunks": 2}

    pipeline = RAGPipeline(embedder, store, EchoGenerator(), top_k=2)
    answer = pipeline.ask("How do I allow cross origin requests?")
    assert answer.sources[0].chunk.document_id == "tutorial/cors"
    assert answer.sources[0].score > answer.sources[1].score


def test_reingest_is_idempotent(conn, embedder):
    store = ChunkStore(conn)
    ingest_documents(DOCS, store, embedder, 1000, 100)
    again = ingest_documents(DOCS, store, embedder, 1000, 100)
    assert again == {"documents": 0, "skipped": 2, "chunks": 0}
    assert store.count_chunks() == 2


def test_changed_document_replaces_old_chunks(conn, embedder):
    store = ChunkStore(conn)
    ingest_documents(DOCS, store, embedder, 1000, 100)
    edited = Document(DOCS[0].id, DOCS[0].title, DOCS[0].url, DOCS[0].text + "\n\nNew paragraph.")
    stats = ingest_documents([edited], store, embedder, 1000, 100)
    assert stats["documents"] == 1
    assert store.count_chunks() == 2  # replaced, not duplicated


def test_empty_index_skips_llm(conn, embedder):
    pipeline = RAGPipeline(embedder, ChunkStore(conn), EchoGenerator(), top_k=3)
    assert pipeline.ask("anything").text == NOT_FOUND


def test_changing_ingestion_settings_reingests(conn, embedder):
    ingest_documents(DOCS, ChunkStore(conn, "1200:200:model-a"), embedder, 1000, 100)
    stats = ingest_documents(DOCS, ChunkStore(conn, "400:50:model-a"), embedder, 1000, 100)
    assert stats["documents"] == 2  # new settings: nothing is "unchanged"
