"""Ingestion: documents -> chunks -> vectors -> Postgres."""

import logging

from rag.embeddings import Embedder
from rag.ingest.chunker import chunk_document
from rag.models import Document
from rag.store import ChunkStore

log = logging.getLogger(__name__)


def ingest_documents(
    docs: list[Document],
    store: ChunkStore,
    embedder: Embedder,
    chunk_size: int,
    chunk_overlap: int,
) -> dict[str, int]:
    stats = {"documents": 0, "skipped": 0, "chunks": 0, "deleted": 0}
    for doc in docs:
        if store.is_unchanged(doc):
            stats["skipped"] += 1  # same content hash: no need to re-embed
            continue
        chunks = chunk_document(doc, chunk_size, chunk_overlap)
        vectors = embedder.embed_documents([c.text for c in chunks])
        store.replace_document(doc, chunks, vectors)
        stats["documents"] += 1
        stats["chunks"] += len(chunks)
        log.info("ingested %s (%d chunks)", doc.id, len(chunks))
    # The source is the truth: anything indexed that is no longer in it goes.
    # Safety net: never wipe the index because the loader returned nothing.
    if docs:
        stats["deleted"] = store.delete_missing([d.id for d in docs])
    return stats
