"""Database connection and schema.

Used by ingestion step 3 (create tables) and by the API at startup (connect).

We use plain Postgres with the pgvector extension instead of a dedicated vector
database. One system holds the text, the metadata and the vectors, so we get
transactions, joins, backups and SQL filtering for free. That is a sensible default
until you have tens of millions of vectors.
"""

import logging

import psycopg
from pgvector.psycopg import register_vector

from rag.dburl import redact, require_tls

log = logging.getLogger("rag.db")

# Two tables. One row in `documents` per page, many rows in `chunks` per page:
#
#   documents                         chunks
#   id = "tutorial/query-params"  <-- document_id, chunk_index 0, content, embedding
#                                 <-- document_id, chunk_index 1, content, embedding
#
# {dim} is filled in from settings (384 for bge-small) by init_schema().
SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id           text PRIMARY KEY,
    title        text NOT NULL,
    url          text NOT NULL,
    content_hash text NOT NULL,          -- lets re-ingestion skip unchanged pages
    ingested_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id          bigserial PRIMARY KEY,
    document_id text NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index int  NOT NULL,
    heading     text NOT NULL,
    url         text NOT NULL,
    content     text NOT NULL,
    embedding   vector({dim}) NOT NULL,
    UNIQUE (document_id, chunk_index)
);

-- HNSW: an approximate nearest-neighbour index. Search is a fast graph walk
-- instead of comparing the query against every row. vector_cosine_ops matches
-- the <=> (cosine distance) operator we query with.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- KEYWORD SEARCH (step 2b). A second way to find chunks: by the exact words in
-- them, next to the vector search above, which finds them by meaning.
--
-- tsv holds each chunk's words, normalised for search:
--   "How do I use response_model_exclude_unset after returning a response?"
--   -> 'exclud':7 'model':6 'respons':5,12 'return':10 'unset':8 'use':4
-- Stop words ("how", "do", "I") are dropped, words are stemmed ("returning" ->
-- "return"), and underscores split code names into words.
--
-- GENERATED ALWAYS ... STORED: Postgres computes the column itself on every
-- insert, so the ingestion code doesn't change at all. ADD COLUMN IF NOT EXISTS
-- also fills it in for rows that are already there: no re-ingest needed.
--
-- setweight A/B: a word in the heading counts more than the same word in the body.
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', heading), 'A') ||
    setweight(to_tsvector('english', content), 'B')
) STORED;

-- GIN: an inverted index (word -> list of rows that contain it), the same idea as
-- the index at the back of a book. It makes "which chunks contain these words?"
-- fast without reading every row.
CREATE INDEX IF NOT EXISTS chunks_tsv_gin ON chunks USING gin (tsv);
"""


def connect(database_url: str) -> psycopg.Connection:
    """Open one connection to Postgres, ready to send and receive vectors.

    database_url looks like postgresql://user:password@host:5432/dbname
    (defaults to the docker-compose database, see config.py).
    """
    # autocommit=True: every statement is saved immediately, EXCEPT inside a
    # `with conn.transaction():` block, which is one real all-or-nothing
    # transaction that COMMITs when the block ends (see store.py).
    #
    # Why not autocommit=False? Then the first SELECT silently opens a transaction
    # that stays open, and `conn.transaction()` blocks inside it become mere
    # savepoints that never commit. That was a real bug here: ingestion reported
    # "661 chunks in total" (visible on its own connection), then the process
    # exited, Postgres rolled everything back, and the table was empty.
    # tests/test_pipeline.py::test_ingested_rows_are_committed guards against it.
    require_tls(database_url)  # a remote database must force TLS (dburl.py)
    log.info("connecting to %s", redact(database_url))  # never the password
    conn = psycopg.connect(database_url, autocommit=True)
    # The extension must exist before register_vector can look up the type.
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    register_vector(conn)  # teach psycopg to send/receive the vector type
    return conn


def init_schema(conn: psycopg.Connection, dim: int) -> None:
    """Create tables and index if they don't exist yet. Safe to call on every run."""
    # int(dim) guards against SQL injection through the setting: only a number
    # can end up in the statement.
    with conn.cursor() as cur:
        cur.execute(SCHEMA.replace("{dim}", str(int(dim))))
