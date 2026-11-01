"""Retrieval: find the chunks the LLM will read. Four modes, so each idea can be measured.

Used by question step 2 (pipeline.py) and by the retrieval eval (evals/retrieval.py).

THE FOUR MODES (set RETRIEVAL_MODE in .env, or compare all of them with
`make eval-retrieval`, which runs every mode on the golden set)

    vector         embed the question, take the k nearest chunks       (step 1)
    hybrid         vector top N + keyword top N, merged with RRF, take k
    rerank         vector top N, re-scored by a cross-encoder, take k   (default)
    hybrid_rerank  hybrid top N, re-scored by a cross-encoder, take k
N = CANDIDATE_K (default 10). Why rerank with N=10 won, with the numbers:
docs/learning/02b-hybrid-search-rerank.md, section 7.

Why four and not just "the best one": if we only built hybrid_rerank and it
scored higher, we wouldn't know which half helped. Each mode adds ONE idea, so
the eval tells us what each idea is worth, and whether it pays for its latency.

WHAT HAPPENS IN hybrid_rerank, IN ORDER (the other modes skip some steps)
    1. vector search: N candidates by meaning               -> store.py search
    2. keyword search: N candidates by exact words          -> store.py keyword_search
    3. RRF: merge the two ranked lists into one             -> rrf() below
    4. rerank: a cross-encoder reads (question, chunk) for
       each of the top 30 and scores it again; keep the top k  -> CrossEncoderReranker

Steps 1-3 are cheap (milliseconds). Step 4 runs a model 30 times per question,
which is why it only sees 30 candidates and not all 661 chunks.
"""

from collections.abc import Sequence
from typing import Literal, Protocol

from rag.embeddings import Embedder
from rag.models import RetrievedChunk
from rag.store import ChunkStore

Mode = Literal["vector", "hybrid", "rerank", "hybrid_rerank"]
MODES: tuple[Mode, ...] = ("vector", "hybrid", "rerank", "hybrid_rerank")


def rrf(ranked_lists: Sequence[list[RetrievedChunk]], k: int = 60) -> list[RetrievedChunk]:
    """Reciprocal Rank Fusion: merge several ranked lists into one.

    The problem: vector search scores are cosine similarities (0.70-0.85 here),
    keyword scores are ts_rank_cd values (0.01-2.0). Adding them makes no sense:
    the scales are unrelated. RRF ignores the scores and uses only the RANKS:

        score(chunk) = sum over the lists it appears in of 1 / (k + rank)

    Worked example, k = 60:
        vector list:   [A, B, C]        keyword list:  [C, D, A]
        A: 1/(60+1) + 1/(60+3) = 0.0164 + 0.0159 = 0.0323
        C: 1/(60+3) + 1/(60+1) = 0.0159 + 0.0164 = 0.0323
        B: 1/(60+2)            = 0.0161
        D: 1/(60+2)            = 0.0161
        -> [A, C, B, D]: chunks that BOTH searches found rise to the top.

    k = 60 is the value from the original paper (Cormack et al., 2009). A large
    k flattens the curve, so being 1st vs 3rd in one list matters less than
    appearing in both lists. It is rarely worth tuning.
    """
    scores: dict[tuple[str, int], float] = {}
    first_seen: dict[tuple[str, int], RetrievedChunk] = {}
    for results in ranked_lists:
        for rank, r in enumerate(results, start=1):
            key = (r.chunk.document_id, r.chunk.index)  # the same chunk in both lists
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(key, r)
    ordered = sorted(scores, key=scores.get, reverse=True)
    return [RetrievedChunk(first_seen[key].chunk, scores[key]) for key in ordered]


class Reranker(Protocol):
    """Anything that scores (question, text) pairs. Tests use a fake one."""

    def score(self, question: str, texts: Sequence[str]) -> list[float]: ...


class CrossEncoderReranker:
    """A cross-encoder: reads the question and one chunk TOGETHER, outputs one score.

    Compare with the embedding model (a bi-encoder):
        bi-encoder:     question -> vector,  chunk -> vector (computed at ingest),
                        score = cosine(vector, vector). Fast, but the model never
                        sees the question and the chunk at the same time.
        cross-encoder:  "[question] [SEP] [chunk]" -> model -> one relevance score.
                        Attention can match every question word against every
                        chunk word, so it is much more precise. Nothing can be
                        precomputed, so it costs one model run per pair.

    The default, Xenova/ms-marco-MiniLM-L-6-v2 (~80MB, ONNX, CPU), was trained on
    MS MARCO: real Bing queries paired with the passages that answered them.
    That is exactly our task: "does this passage answer this question?"
    Scores are raw logits (e.g. -9.1 ... 7.4): only their ORDER matters.
    """

    def __init__(self, model_name: str):
        # Same reason as in embeddings.py: heavy import, done once at startup.
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model = TextCrossEncoder(model_name=model_name)

    def score(self, question: str, texts: Sequence[str]) -> list[float]:
        return [float(s) for s in self.model.rerank(question, list(texts), batch_size=32)]


class Retriever:
    """Runs one retrieval mode. Created once (API startup, CLI, eval) and reused."""

    def __init__(
        self,
        store: ChunkStore,
        embedder: Embedder,
        mode: Mode = "vector",
        reranker: Reranker | None = None,
        candidate_k: int = 30,
        rrf_k: int = 60,
    ):
        if mode not in MODES:
            raise ValueError(f"unknown retrieval mode {mode!r}, expected one of {MODES}")
        if "rerank" in mode and reranker is None:
            raise ValueError(f"mode {mode!r} needs a reranker")
        self.store = store
        self.embedder = embedder
        self.mode = mode
        self.reranker = reranker
        self.candidate_k = candidate_k  # how many candidates the cheap stages pass on
        self.rrf_k = rrf_k

    def retrieve(self, question: str, k: int) -> list[RetrievedChunk]:
        # Plain vector search fetches exactly k. Every other mode fetches a wider
        # pool first (candidate_k, default 10), because merging or re-ordering can
        # only promote a chunk that is somewhere in the pool. A bigger pool is not
        # always better: at 30 the reranker promoted wrong chunks from far down
        # the list and broke 4 questions; at 10 it broke none.
        pool = k if self.mode == "vector" else max(k, self.candidate_k)

        # 1. Vector search: always runs.
        results = self.store.search(self.embedder.embed_query(question), pool)

        # 2 + 3. Keyword search, merged with the vector list by rank.
        if self.mode in ("hybrid", "hybrid_rerank"):
            keyword = self.store.keyword_search(question, pool)
            results = rrf([results, keyword], k=self.rrf_k)[:pool]

        # 4. Rerank: score every candidate with the cross-encoder, best first.
        if self.reranker is not None and "rerank" in self.mode and results:
            scores = self.reranker.score(question, [r.chunk.text for r in results])
            ranked = sorted(zip(results, scores, strict=True), key=lambda p: p[1], reverse=True)
            results = [RetrievedChunk(r.chunk, s) for r, s in ranked]

        # Note: the .score of what we return depends on the mode (cosine, RRF or
        # cross-encoder logit). Compare scores only within one mode.
        return results[:k]


def build_retriever(store: ChunkStore, embedder: Embedder, mode: Mode | None = None) -> Retriever:
    """Build a Retriever from settings. mode overrides RETRIEVAL_MODE (the eval uses it)."""
    from rag.config import get_settings

    s = get_settings()
    mode = mode or s.retrieval_mode
    reranker = CrossEncoderReranker(s.reranker_model) if "rerank" in mode else None
    return Retriever(store, embedder, mode, reranker, s.candidate_k, s.rrf_k)
