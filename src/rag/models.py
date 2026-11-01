"""Plain data objects that move between the pipeline stages."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Document:
    """One source page, before chunking."""

    id: str  # stable id, e.g. "tutorial/query-params"
    title: str
    url: str
    text: str  # markdown, with code examples inlined


@dataclass(frozen=True)
class Chunk:
    """A piece of a document small enough to embed and to put in a prompt."""

    document_id: str
    index: int  # position inside the document
    heading: str  # "Query Parameters > Defaults"
    url: str  # deep link to the section
    text: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float  # cosine similarity, higher is closer


@dataclass
class Answer:
    text: str
    sources: list[RetrievedChunk]  # what we gave the model
    cited: list[int] = field(default_factory=list)  # 1-based source numbers the model cited
    usage: dict = field(default_factory=dict)
