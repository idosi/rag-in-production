"""Retrieve, then generate. The whole RAG idea in one class."""

from rag.embeddings import Embedder
from rag.generator import NOT_FOUND, Generator
from rag.models import Answer
from rag.store import ChunkStore


class RAGPipeline:
    def __init__(self, embedder: Embedder, store: ChunkStore, generator: Generator, top_k: int):
        self.embedder = embedder
        self.store = store
        self.generator = generator
        self.top_k = top_k

    def ask(self, question: str) -> Answer:
        query_vector = self.embedder.embed_query(question)
        sources = self.store.search(query_vector, self.top_k)
        if not sources:
            # Nothing indexed: don't pay for an LLM call that can only fail.
            return Answer(text=NOT_FOUND, sources=[])
        return self.generator.generate(question, sources)


def build_pipeline() -> RAGPipeline:
    """Wire the real components together from settings."""
    from rag.config import get_settings
    from rag.db import connect
    from rag.embeddings import FastEmbedEmbedder
    from rag.generator import ClaudeGenerator

    s = get_settings()
    return RAGPipeline(
        embedder=FastEmbedEmbedder(s.embedding_model, s.embedding_dim),
        store=ChunkStore(connect(s.database_url)),
        generator=ClaudeGenerator(s.llm_model, s.llm_effort, s.llm_max_tokens),
        top_k=s.top_k,
    )
