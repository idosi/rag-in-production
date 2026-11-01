"""Turn text into vectors.

Used in TWO places:
  - Ingestion step 5c: embed_documents() on every chunk      (offline, once)
  - Question step 1:   embed_query() on the user's question  (online, every request)
Both must use the SAME model, or the vectors live in different "maps" and
comparing them is meaningless.

An embedding model maps text to a point in a high-dimensional space where texts
with similar meaning land close together. "How do I read query params?" and a
chunk explaining query parameters end up near each other even when they share
few exact words.

Concretely, for bge-small-en-v1.5:
    "How do I make a query parameter optional?"  ->  [0.021, -0.043, ..., 0.017]
                                                     (384 floats, vector length 1.0)

The pipeline depends on the `Embedder` protocol, not on a concrete model, so we can
swap the model (or use a fake one in tests) without touching anything else.
"""

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    """The interface: any class with these members can be used as an embedder.

    A Protocol is Python's version of a Java interface, except a class doesn't
    have to declare "implements": having the right methods is enough (duck typing).
    tests/conftest.py has a FakeEmbedder that satisfies it with no model at all.
    """

    dim: int  # vector length; must match the vector(N) column in db.py

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Local ONNX embedding model. No API key, no per-call cost, runs on CPU.

    BGE models are trained "asymmetric": queries get an instruction prefix and
    passages do not. fastembed's query_embed / passage_embed apply that for us.
    Using the same method for both would quietly hurt retrieval quality.
    """

    def __init__(self, model_name: str, dim: int):
        # Imported here, not at the top of the file: loading fastembed/ONNX takes
        # a moment, and tests that never build a real embedder shouldn't pay it.
        from fastembed import TextEmbedding

        # First time: downloads the model files (~130MB) to a local cache.
        # After that: loads them from disk. Either way, done ONCE per process,
        # which is why the API builds the embedder at startup, not per request.
        self.model = TextEmbedding(model_name=model_name)
        self.dim = dim

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        # passage_embed is a generator of numpy arrays, processed 32 texts at a
        # time. .tolist() converts each to a plain list of floats.
        return [v.tolist() for v in self.model.passage_embed(list(texts), batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        # query_embed also returns a generator; we passed one text, so take the
        # first (and only) vector.
        return next(iter(self.model.query_embed(text))).tolist()
