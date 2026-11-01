"""Ingestion entry point: builds the searchable index from the FastAPI docs.

HOW TO RUN
    make ingest              (same as: uv run python -m rag.ingest)

`python -m rag.ingest` runs this file because it is the package's __main__.py.

WHAT HAPPENS, IN ORDER (follow the numbers into the other files)
    1. Load settings from .env / environment         -> config.py
    2. Download 43 pages, inline code examples       -> ingest/loader.py
    3. Connect to Postgres, create tables + index    -> db.py
    4. Load the embedding model into memory          -> embeddings.py
    5. For every page:                               -> ingest/pipeline.py
         5a. unchanged since last run? skip it       -> store.py  (is_unchanged)
         5b. split it into chunks                    -> ingest/chunker.py
         5c. turn each chunk into a vector           -> embeddings.py
         5d. replace the page's rows in one TX       -> store.py  (replace_document)
    6. Delete pages that no longer exist upstream    -> store.py  (delete_missing)

This is the OFFLINE path. It runs once, or when the docs change, never per question.
Everything expensive that can be computed ahead of time is computed here, so the
online path (answering a question) stays fast and cheap.
"""

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
    # Libraries log every HTTP request at INFO level (~200 lines here). Show only
    # their warnings, so our own progress lines stay readable.
    for noisy in ("httpx", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    start = time.perf_counter()

    # 1. Settings: chunk size, model names, DB URL... (defaults in config.py,
    #    overridable from .env). Nothing below hard-codes a tunable value.
    s = get_settings()

    # 2. Download the pages (or read them from the data/raw/ disk cache).
    #    Result: a list of Document(id, title, url, text), one per page.
    docs = load_documents(s.docs_version, s.docs_cache_dir)
    print(f"Loaded {len(docs)} pages (FastAPI docs {s.docs_version})")

    # 3. Open a DB connection and make sure the tables and the vector index exist.
    #    Safe to run every time: the SQL uses CREATE ... IF NOT EXISTS.
    conn = connect(s.database_url)
    init_schema(conn, s.embedding_dim)

    # The fingerprint is mixed into each page's content hash. If you change how
    # chunks are made (size, overlap) or embedded (model), every page's hash
    # changes, so step 5a re-processes everything instead of keeping stale chunks.
    fingerprint = f"{s.chunk_size}:{s.chunk_overlap}:{s.embedding_model}"
    store = ChunkStore(conn, fingerprint)

    # 4. Load the embedding model. The first run downloads it (~130MB) into a
    #    local cache. This is the slowest line on a first run.
    embedder = FastEmbedEmbedder(s.embedding_model, s.embedding_dim)

    # 5 + 6. The actual work: chunk -> embed -> store, page by page.
    stats = ingest_documents(docs, store, embedder, s.chunk_size, s.chunk_overlap)

    print(
        f"Done in {time.perf_counter() - start:.1f}s: "
        f"{stats['documents']} ingested, {stats['skipped']} unchanged, "
        f"{stats['deleted']} removed, {stats['chunks']} new chunks, "
        f"{store.count_chunks()} chunks in total"
    )
    # Try running it twice: the second run should say "43 unchanged" and finish
    # in seconds. That is idempotency (see docs/learning/01-foundations.md, 4.5).


if __name__ == "__main__":
    main()
