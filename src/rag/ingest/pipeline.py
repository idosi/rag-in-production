"""Ingestion loop: documents -> chunks -> vectors -> Postgres.

Called by ingest/__main__.py (step 5 and 6 there). Kept separate from __main__ so
tests can call it with a fake embedder and a test database (tests/test_pipeline.py).
"""

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
    """Index every document and return counts of what happened."""
    stats = {"documents": 0, "skipped": 0, "chunks": 0, "deleted": 0}

    for doc in docs:
        # 5a. Compare this page's hash to the one stored on the last run.
        #     Same hash = same text and same settings = the stored chunks are
        #     still correct. Skipping saves the embedding time (and, with a paid
        #     embedding API, money).
        if store.is_unchanged(doc):
            stats["skipped"] += 1
            continue

        # 5b. One page (a few thousand characters of markdown) becomes a list of
        #     Chunk objects of up to chunk_size characters each, for example:
        #       Chunk(heading="Query Parameters > Defaults",
        #             url=".../query-params/#defaults",
        #             text="Query Parameters > Defaults\n\nAs query parameters ...")
        chunks = chunk_document(doc, chunk_size, chunk_overlap)

        # 5c. Each chunk's text becomes a vector of 384 floats. We embed the whole
        #     page's chunks in one call: models are much faster in batches than
        #     one text at a time. vectors[i] belongs to chunks[i].
        vectors = embedder.embed_documents([c.text for c in chunks])

        # 5d. Write the page and its chunks. Inside one transaction the old rows
        #     are deleted and the new ones inserted, so a question asked at this
        #     very moment sees the old page or the new page, never half of each.
        store.replace_document(doc, chunks, vectors)

        stats["documents"] += 1
        stats["chunks"] += len(chunks)
        log.info("ingested %s (%d chunks)", doc.id, len(chunks))

    # 6. The source is the truth: a page that is in the DB but not in this load
    #    was removed upstream, so it must not be cited any more.
    #    Safety net: an empty load (e.g. the network was down) is far more likely
    #    to be a bug than "the docs were deleted", so in that case delete nothing.
    if docs:
        stats["deleted"] = store.delete_missing([d.id for d in docs])

    return stats
