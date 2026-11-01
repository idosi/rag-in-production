"""python -m rag.ingest"""

import logging
import time

from rag.config import get_settings
from rag.db import connect, init_schema
from rag.embeddings import FastEmbedEmbedder
from rag.ingest.loader import load_documents
from rag.ingest.pipeline import ingest_documents
from rag.store import ChunkStore


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    s = get_settings()
    start = time.perf_counter()

    docs = load_documents(s.docs_version, s.docs_cache_dir)
    print(f"Loaded {len(docs)} pages (FastAPI docs {s.docs_version})")

    conn = connect(s.database_url)
    init_schema(conn, s.embedding_dim)
    fingerprint = f"{s.chunk_size}:{s.chunk_overlap}:{s.embedding_model}"
    store = ChunkStore(conn, fingerprint)
    embedder = FastEmbedEmbedder(s.embedding_model, s.embedding_dim)

    stats = ingest_documents(docs, store, embedder, s.chunk_size, s.chunk_overlap)
    print(
        f"Done in {time.perf_counter() - start:.1f}s: "
        f"{stats['documents']} ingested, {stats['skipped']} unchanged, "
        f"{stats['chunks']} new chunks, {store.count_chunks()} chunks in total"
    )


if __name__ == "__main__":
    main()
