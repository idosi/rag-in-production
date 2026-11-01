"""Turn text into vectors.

An embedding model maps text to a point in a high-dimensional space where texts
with similar meaning land close together. "How do I read query params?" and a
chunk explaining query parameters end up near each other even when they share
few exact words.

The pipeline depends on the `Embedder` protocol, not on a concrete model, so we can
swap the model (or use a fake one in tests) without touching anything else.
"""

from collections.abc import Sequence
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """Local ONNX embedding model. No API key, no per-call cost, runs on CPU.

    BGE models are trained "asymmetric": queries get an instruction prefix and
    passages do not. fastembed's query_embed / passage_embed apply that for us.
    Using the same method for both would quietly hurt retrieval quality.
    """

    def __init__(self, model_name: str, dim: int):
        from fastembed import TextEmbedding  # heavy import, load only when used

        self.model = TextEmbedding(model_name=model_name)
        self.dim = dim

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [v.tolist() for v in self.model.passage_embed(list(texts), batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self.model.query_embed(text))).tolist()
