"""Read and write chunks in Postgres. All SQL in the project lives here.

Writers (ingestion):  is_unchanged -> replace_document -> delete_missing
Reader  (questions):  search

Note on `%s` / `%(q)s` in the SQL below: those are query PARAMETERS. psycopg sends
the values separately from the SQL text, so user input can never change the query
(no SQL injection). Never build SQL with f-strings from user input.
"""

import hashlib

import numpy as np
import psycopg

from rag.models import Chunk, Document, RetrievedChunk


def content_hash(doc: Document, fingerprint: str = "") -> str:
    """Hash of the page text plus the ingestion settings that shaped its chunks.

    Including the fingerprint (chunk size, overlap, embedding model) means that
    changing any of those re-ingests the page, instead of silently keeping chunks
    made with the old settings.
    """
    return hashlib.sha256(f"{fingerprint}\n{doc.text}".encode()).hexdigest()


class ChunkStore:
    """Wraps one DB connection. Created once and reused (by ingestion or by the API)."""

    def __init__(self, conn: psycopg.Connection, fingerprint: str = ""):
        self.conn = conn
        self.fingerprint = fingerprint

    def is_unchanged(self, doc: Document) -> bool:
        """True if this page was already ingested with the same text and settings."""
        with self.conn.cursor() as cur:
            cur.execute("SELECT content_hash FROM documents WHERE id = %s", (doc.id,))
            row = cur.fetchone()
        return row is not None and row[0] == content_hash(doc, self.fingerprint)

    def replace_document(
        self, doc: Document, chunks: list[Chunk], vectors: list[list[float]]
    ) -> None:
        """Swap a document's chunks atomically.

        Delete + insert happen in one transaction: a reader sees either the old
        version or the new one, never a half-ingested page. Running ingestion twice
        gives the same result (idempotent), which is what makes it safe to re-run.
        """
        # `with conn.transaction()`: COMMIT if the block finishes, ROLLBACK if any
        # line inside raises. So either all three statements happen, or none.
        with self.conn.transaction(), self.conn.cursor() as cur:
            # ON DELETE CASCADE (db.py) removes the page's old chunks too.
            cur.execute("DELETE FROM documents WHERE id = %s", (doc.id,))
            cur.execute(
                "INSERT INTO documents (id, title, url, content_hash) VALUES (%s, %s, %s, %s)",
                (doc.id, doc.title, doc.url, content_hash(doc, self.fingerprint)),
            )
            # executemany: one INSERT per chunk, sent efficiently in a batch.
            # np.array(v) lets pgvector convert the list of floats to a vector.
            # strict=True fails loudly if chunks and vectors ever differ in length.
            cur.executemany(
                """INSERT INTO chunks (document_id, chunk_index, heading, url, content, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [
                    (c.document_id, c.index, c.heading, c.url, c.text, np.array(v))
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )

    def delete_missing(self, keep_ids: list[str]) -> int:
        """Delete every document not in keep_ids (and, by cascade, its chunks).

        Without this, a page removed from the source stays in the index forever
        and keeps being cited: the system would serve answers that are no longer true.
        """
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE NOT (id = ANY(%s))", (keep_ids,))
            return cur.rowcount

    def search(self, query_vector: list[float], k: int) -> list[RetrievedChunk]:
        """Return the k chunks closest to the query vector.

        `<=>` is pgvector's cosine distance (0 = same direction, 2 = opposite).
        We report similarity = 1 - distance so that higher means more relevant.
        """
        # The whole retrieval step is this one query:
        #   - compute the distance between the question vector and every chunk
        #   - sort by it, closest first
        #   - keep the first k
        # The HNSW index (db.py) makes the ORDER BY fast without scanning every row.
        with self.conn.cursor() as cur:
            cur.execute(
                """SELECT document_id, chunk_index, heading, url, content,
                          1 - (embedding <=> %(q)s) AS score
                   FROM chunks
                   ORDER BY embedding <=> %(q)s
                   LIMIT %(k)s""",
                {"q": np.array(query_vector), "k": k},
            )
            rows = cur.fetchall()
        # Turn raw DB rows (tuples) back into typed objects for the rest of the code.
        return [
            RetrievedChunk(
                chunk=Chunk(document_id=r[0], index=r[1], heading=r[2], url=r[3], text=r[4]),
                score=float(r[5]),
            )
            for r in rows
        ]

    def count_chunks(self) -> int:
        with self.conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM chunks")
            return cur.fetchone()[0]
