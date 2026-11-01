import hashlib
import math
import os
import re

import psycopg
import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag")


class FakeEmbedder:
    """Deterministic bag-of-words embedder: no model download, no network.

    Texts that share words get similar vectors, which is enough to test that
    retrieval returns the right chunk.
    """

    dim = 64

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for word in re.findall(r"[a-z]+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def conn():
    """A fresh schema per test. Skips if Postgres is not running."""
    from rag.db import connect, init_schema

    try:
        c = connect(TEST_DB)
    except psycopg.OperationalError:
        pytest.skip("Postgres not available (run `make up`)")
    with c.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS chunks, documents CASCADE")
    c.commit()
    init_schema(c, FakeEmbedder.dim)
    yield c
    with c.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS chunks, documents CASCADE")
    c.commit()
    c.close()
