import hashlib
import math
import os
import re

import psycopg
import pytest

# Tests use their OWN database (rag_test) on the same Postgres server, because the
# fixture below drops and recreates the tables. Pointing tests at the dev database
# would wipe the index that `make ingest` built.
ADMIN_DB = os.environ.get("TEST_ADMIN_DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag")
TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql://rag:rag@localhost:5432/rag_test")


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


@pytest.fixture(scope="session")
def test_database():
    """Create the rag_test database once per test run, if it doesn't exist yet."""
    try:
        with psycopg.connect(ADMIN_DB, autocommit=True) as admin:
            exists = admin.execute(
                "SELECT 1 FROM pg_database WHERE datname = 'rag_test'"
            ).fetchone()
            if not exists:
                # CREATE DATABASE can't run inside a transaction, hence autocommit.
                admin.execute("CREATE DATABASE rag_test")
    except psycopg.OperationalError:
        pytest.skip("Postgres not available (run `make up`)")
    return TEST_DB


@pytest.fixture
def conn(test_database):
    """A fresh schema per test, in the rag_test database."""
    from rag.db import connect, init_schema

    c = connect(test_database)
    with c.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS chunks, documents CASCADE")
    c.commit()
    init_schema(c, FakeEmbedder.dim)
    yield c
    with c.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS chunks, documents CASCADE")
    c.commit()
    c.close()
