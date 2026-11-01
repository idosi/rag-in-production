"""Read and write chunks in Postgres."""

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
    def __init__(self, conn: psycopg.Connection, fingerprint: str = ""):
        self.conn = conn
        self.fingerprint = fingerprint

    def is_unchanged(self, doc: Document) -> bool:
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
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE id = %s", (doc.id,))  # cascades to chunks
            cur.execute(
                "INSERT INTO documents (id, title, url, content_hash) VALUES (%s, %s, %s, %s)",
                (doc.id, doc.title, doc.url, content_hash(doc, self.fingerprint)),
            )
            cur.executemany(
                """INSERT INTO chunks (document_id, chunk_index, heading, url, content, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [
                    (c.document_id, c.index, c.heading, c.url, c.text, np.array(v))
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )

    def search(self, query_vector: list[float], k: int) -> list[RetrievedChunk]:
        """Return the k chunks closest to the query vector.

        `<=>` is pgvector's cosine distance (0 = same direction, 2 = opposite).
        We report similarity = 1 - distance so that higher means more relevant.
        """
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
