"""Plain data objects that move between the pipeline stages.

How data changes shape on its way through the system:

    INGESTION                                   QUESTION
    Document  (one page)                        question: str
       |  chunker.py                               |  embeddings.py
    Chunk     (one piece of a page)             vector: list[float]
       |  embeddings.py + store.py                 |  store.py
    row in Postgres (chunk + vector)  ------>   RetrievedChunk (chunk + score)
                                                   |  generator.py
                                                Answer (text + sources + citations)

frozen=True makes an object immutable: once created, its fields can't change.
That rules out a whole class of bugs where one stage modifies data another stage
is still using.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Document:
    """One source page, before chunking."""

    id: str  # stable id, e.g. "tutorial/query-params"
    title: str  # "Query Parameters"
    url: str  # "https://fastapi.tiangolo.com/tutorial/query-params/"
    text: str  # the page's markdown, with code examples inlined


@dataclass(frozen=True)
class Chunk:
    """A piece of a document small enough to embed and to put in a prompt."""

    document_id: str  # which Document it came from
    index: int  # position inside the document: 0, 1, 2, ...
    heading: str  # "Query Parameters > Defaults"
    url: str  # deep link to the section: ".../query-params/#defaults"
    text: str  # heading + body; this is what gets embedded and shown to the LLM


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk returned by search, with how well it matched the question."""

    chunk: Chunk
    score: float  # cosine similarity: ~0.8+ very close, ~0.5 loosely related


@dataclass
class Answer:
    """What the pipeline returns to the API / CLI."""

    text: str  # the model's answer, with [n] markers
    sources: list[RetrievedChunk]  # what we gave the model, in [1], [2], ... order
    cited: list[int] = field(default_factory=list)  # which of those the answer cited
    usage: dict = field(default_factory=dict)  # model name and token counts
