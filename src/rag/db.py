"""Database connection and schema.

We use plain Postgres with the pgvector extension instead of a dedicated vector
database. One system holds the text, the metadata and the vectors, so we get
transactions, joins, backups and SQL filtering for free. That is a sensible default
until you have tens of millions of vectors.
"""

import psycopg
from pgvector.psycopg import register_vector

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
"""


def connect(database_url: str) -> psycopg.Connection:
    conn = psycopg.connect(database_url, autocommit=False)
    with conn.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    register_vector(conn)  # teach psycopg to send/receive the vector type
    return conn


def init_schema(conn: psycopg.Connection, dim: int) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA.replace("{dim}", str(int(dim))))
    conn.commit()
