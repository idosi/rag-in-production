"""Retrieve, then generate. The whole RAG idea in one class.

This is the ONLINE path: it runs for every question, from the API (api.py) or the
CLI (ask.py). The index it searches was built beforehand by `make ingest`.

WHAT HAPPENS FOR ONE QUESTION, IN ORDER
    1+2. question -> the 5 most relevant chunks      -> retrieval.py   retrieve
         (embed + vector search; in the hybrid/rerank modes also keyword
         search, RRF and a cross-encoder, see retrieval.py)
    3. if nothing was found, stop (no LLM call)
    4. question + 5 chunks -> Claude -> answer       -> generator.py   generate
       with [n] citations

Typical cost: retrieval takes milliseconds (vector) to a few hundred ms (with
the reranker) on CPU; step 4 takes seconds and is the only step that costs
money per question.
"""

from rag.generator import NOT_FOUND, Generator
from rag.models import Answer
from rag.retrieval import Retriever
from rag.trace import span


class RAGPipeline:
    """Holds the two components (retriever, generator) and runs them in order.

    It receives its components instead of creating them (dependency injection).
    Production code passes the real ones (build_pipeline below); tests pass fakes
    (tests/test_pipeline.py), so the flow can be tested with no model and no API key.
    """

    def __init__(self, retriever: Retriever, generator: Generator, top_k: int):
        self.retriever = retriever
        self.generator = generator
        self.top_k = top_k  # how many chunks to give the LLM (default 5, see config.py)

    def ask(self, question: str) -> Answer:
        # 1+2. Retrieval: the k chunks most likely to answer the question. In
        #      "vector" mode: embed the question, take the k nearest chunks.
        #      The other modes add keyword search and/or reranking (retrieval.py).
        with span("retrieve"):
            sources = self.retriever.retrieve(question, self.top_k)

        # 3. Empty index (ingest never ran): an LLM call could only fail, and
        #    it would cost money. Answer "not found" right away.
        if not sources:
            return Answer(text=NOT_FOUND, sources=[])

        # 4. Generation: Claude reads the chunks and answers only from them.
        with span("generate"):
            return self.generator.generate(question, sources)


def build_pipeline() -> RAGPipeline:
    """Wire the real components together from settings.

    Called once: at API startup (api.py lifespan) or at CLI start (ask.py).
    Slow parts (loading the embedding and reranker models, opening the DB connection, creating
    the HTTP client for Claude) happen here, so each question doesn't repeat them.
    """
    # Imports inside the function: importing pipeline.py (e.g. in tests) doesn't
    # pull in the heavy model library or require an API key.
    from rag.config import get_settings
    from rag.db import connect, init_schema
    from rag.embeddings import FastEmbedEmbedder
    from rag.generator import ClaudeGenerator
    from rag.retrieval import build_retriever
    from rag.store import ChunkStore

    s = get_settings()
    conn = connect(s.database_url)
    # Idempotent. Here it adds the keyword-search column (step 2b) to an index
    # built before that column existed, so no re-ingest is needed.
    init_schema(conn, s.embedding_dim)
    return RAGPipeline(
        retriever=build_retriever(
            ChunkStore(conn), FastEmbedEmbedder(s.embedding_model, s.embedding_dim)
        ),
        generator=ClaudeGenerator(
            s.llm_model,
            s.llm_effort,
            s.llm_max_tokens,
            api_key=s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None,
        ),
        top_k=s.top_k,
    )
