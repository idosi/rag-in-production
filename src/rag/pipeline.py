"""Retrieve, then generate. The whole RAG idea in one class.

This is the ONLINE path: it runs for every question, from the API (api.py) or the
CLI (ask.py). The index it searches was built beforehand by `make ingest`.

WHAT HAPPENS FOR ONE QUESTION, IN ORDER
    1. question text -> vector (384 floats)          -> embeddings.py  embed_query
    2. vector -> 5 closest chunks from Postgres      -> store.py       search
    3. if nothing was found, stop (no LLM call)
    4. question + 5 chunks -> Claude -> answer       -> generator.py   generate
       with [n] citations

Typical cost of each step: 1 takes ~10ms on CPU, 2 takes a few ms, 4 takes
seconds and is the only step that costs money per question.
"""

from rag.embeddings import Embedder
from rag.generator import NOT_FOUND, Generator
from rag.models import Answer
from rag.store import ChunkStore


class RAGPipeline:
    """Holds the three components and runs them in order.

    It receives its components instead of creating them (dependency injection).
    Production code passes the real ones (build_pipeline below); tests pass fakes
    (tests/test_pipeline.py), so the flow can be tested with no model and no API key.
    """

    def __init__(self, embedder: Embedder, store: ChunkStore, generator: Generator, top_k: int):
        self.embedder = embedder
        self.store = store
        self.generator = generator
        self.top_k = top_k  # how many chunks to give the LLM (default 5, see config.py)

    def ask(self, question: str) -> Answer:
        # 1. Embed the question with the same model that embedded the chunks.
        query_vector = self.embedder.embed_query(question)

        # 2. Retrieval: the k chunks whose vectors point in the most similar
        #    direction. Each comes with a score (cosine similarity, higher = closer).
        sources = self.store.search(query_vector, self.top_k)

        # 3. Empty index (ingest never ran): an LLM call could only fail, and
        #    it would cost money. Answer "not found" right away.
        if not sources:
            return Answer(text=NOT_FOUND, sources=[])

        # 4. Generation: Claude reads the chunks and answers only from them.
        return self.generator.generate(question, sources)


def build_pipeline() -> RAGPipeline:
    """Wire the real components together from settings.

    Called once: at API startup (api.py lifespan) or at CLI start (ask.py).
    Slow parts (loading the embedding model, opening the DB connection, creating
    the HTTP client for Claude) happen here, so each question doesn't repeat them.
    """
    # Imports inside the function: importing pipeline.py (e.g. in tests) doesn't
    # pull in the heavy model library or require an API key.
    from rag.config import get_settings
    from rag.db import connect
    from rag.embeddings import FastEmbedEmbedder
    from rag.generator import ClaudeGenerator

    s = get_settings()
    return RAGPipeline(
        embedder=FastEmbedEmbedder(s.embedding_model, s.embedding_dim),
        store=ChunkStore(connect(s.database_url)),
        generator=ClaudeGenerator(
            s.llm_model,
            s.llm_effort,
            s.llm_max_tokens,
            api_key=s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None,
        ),
        top_k=s.top_k,
    )
