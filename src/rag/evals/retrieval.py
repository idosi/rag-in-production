"""Retrieval evaluation: does search put the right sections in the top k?

HOW TO RUN
    make eval-retrieval                    every retrieval mode, side by side
    make eval-retrieval MODES=vector,rerank   only some modes
    (same as: uv run python -m rag.evals.retrieval --modes vector,rerank)
Prerequisites: `make up` and `make ingest`. No LLM is called, so it costs nothing
and takes seconds (the reranker modes take longer: a model runs per candidate).
Run it before and after every retrieval change.

WHY EVALUATE RETRIEVAL SEPARATELY FROM ANSWERS
The LLM can only answer from what retrieval gives it. If the right section isn't
in the top 5, no prompt or model can fix the answer (we saw this with the
"run code after returning a response" question). Retrieval metrics are also
cheap and deterministic, while judging answers needs an LLM and costs money.

WHAT IT DOES, IN ORDER
    1. Load the golden set: questions + the sections that answer them
       (evals/golden_set.json, labelled by hand as "page#anchor")
    2. For each retrieval mode, for each answerable question: retrieve top MAX_K
    3. Map each retrieved chunk to its section key ("tutorial/body#request-body")
    4. Compute hit@k, recall@k and reciprocal rank for that question
    5. Average per category and overall, print a report, list the misses
    6. Compare the modes: one summary row each, plus which questions each mode
       fixed or broke compared to plain vector search
    7. Save everything to evals/results/ so runs can be compared over time

Labels are SECTIONS, not chunk ids, on purpose: chunk ids change whenever chunk
size changes, section anchors don't. So the same golden set can compare
different chunking settings.
"""

import argparse
import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rag.models import RetrievedChunk

GOLDEN_SET = Path("evals/golden_set.json")
RESULTS_DIR = Path("evals/results")
K_VALUES = (1, 3, 5, 10)
MAX_K = max(K_VALUES)


@dataclass
class QuestionResult:
    id: str
    category: str
    question: str
    relevant: list[str]  # sections that answer it (from the golden set)
    retrieved: list[str]  # section key of each retrieved chunk, best first
    scores: list[float]
    first_hit_rank: int | None  # 1-based rank of the first relevant chunk, None = miss
    hit: dict[int, bool] = field(default_factory=dict)  # k -> any relevant in top k?
    recall: dict[int, float] = field(default_factory=dict)  # k -> share of relevant found


def section_key(r: RetrievedChunk) -> str:
    """'tutorial/query-params' + '.../query-params/#defaults' -> 'tutorial/query-params#defaults'"""
    anchor = r.chunk.url.split("#", 1)[1] if "#" in r.chunk.url else ""
    return f"{r.chunk.document_id}#{anchor}"


def score_question(q: dict, results: list[RetrievedChunk]) -> QuestionResult:
    """Compute the metrics for one question. Pure function: easy to unit test.

    Example: relevant = {A, B}, retrieved sections = [X, A, A, Y, B]
        first_hit_rank = 2          (A is at position 2)
        hit@1 = False, hit@3 = True
        recall@3 = 0.5              (found A; B only appears at position 5)
        recall@5 = 1.0
        reciprocal rank = 1/2
    """
    relevant = set(q["relevant"])
    retrieved = [section_key(r) for r in results]
    first_hit = next((i for i, s in enumerate(retrieved, start=1) if s in relevant), None)
    hit, recall = {}, {}
    for k in K_VALUES:
        found = relevant & set(retrieved[:k])
        hit[k] = bool(found)
        recall[k] = len(found) / len(relevant)
    return QuestionResult(
        id=q["id"],
        category=q["category"],
        question=q["question"],
        relevant=q["relevant"],
        retrieved=retrieved,
        scores=[round(r.score, 4) for r in results],
        first_hit_rank=first_hit,
        hit=hit,
        recall=recall,
    )


def summarize(results: list[QuestionResult]) -> dict:
    """Average the per-question metrics.

    hit@k     share of questions with at least one relevant section in the top k.
              hit@5 is the headline number: we give the LLM 5 chunks.
    recall@k  average share of ALL relevant sections found in the top k.
              Matters for questions whose answer is spread over several sections.
    MRR       mean of 1/rank of the first hit (0 for a miss). 1.0 = always first.
              Rewards putting the right chunk at the top, not just somewhere in it.
    """
    n = len(results)
    if n == 0:
        return {}
    return {
        "questions": n,
        **{f"hit@{k}": round(sum(r.hit[k] for r in results) / n, 3) for k in K_VALUES},
        **{f"recall@{k}": round(sum(r.recall[k] for r in results) / n, 3) for k in K_VALUES},
        "mrr": round(sum(1 / r.first_hit_rank for r in results if r.first_hit_rank) / n, 3),
    }


def run(search, golden: list[dict]) -> list[QuestionResult]:
    """search: function(question, k) -> list[RetrievedChunk]. Injected so tests can fake it."""
    answerable = [q for q in golden if q["relevant"]]  # unanswerable ones are for answer evals
    return [score_question(q, search(q["question"], MAX_K)) for q in answerable]


def diff_hits(base: list[QuestionResult], other: list[QuestionResult], k: int = 5) -> dict:
    """Which questions a mode fixed or broke at k, compared with a base mode.

    The averages can hide trades: +3 fixed and -2 broken looks like a small
    gain, but the 2 broken questions might matter more. Always read this list.
    """
    before = {r.id: r.hit[k] for r in base}
    fixed = [r.id for r in other if r.hit[k] and not before[r.id]]
    broke = [r.id for r in other if before[r.id] and not r.hit[k]]
    return {"fixed": fixed, "broke": broke}


def print_report(results: list[QuestionResult], summary: dict) -> None:
    categories = sorted({r.category for r in results})
    cols = ["hit@1", "hit@3", "hit@5", "hit@10", "recall@5", "mrr"]
    print(f"\n{'category':<12}{'n':>4}" + "".join(f"{c:>10}" for c in cols))
    for cat in [*categories, "ALL"]:
        rows = results if cat == "ALL" else [r for r in results if r.category == cat]
        s = summary if cat == "ALL" else summarize(rows)
        print(f"{cat:<12}{len(rows):>4}" + "".join(f"{s[c]:>10.3f}" for c in cols))

    misses = [r for r in results if not r.hit[5]]
    print(f"\nMisses at k=5 ({len(misses)}):")
    for r in misses:
        rank = f"first hit at rank {r.first_hit_rank}" if r.first_hit_rank else "not in top 10"
        print(f"  {r.id} [{r.category}] {r.question}\n        {rank}; got: {r.retrieved[:3]}")


def main() -> None:
    from rag.config import get_settings
    from rag.db import connect, init_schema
    from rag.embeddings import FastEmbedEmbedder
    from rag.retrieval import ALL_MODES, MODES, CrossEncoderReranker, Retriever
    from rag.store import ChunkStore

    parser = argparse.ArgumentParser(description="Measure retrieval on the golden set.")
    parser.add_argument(
        "--modes",
        default=",".join(MODES),
        help=f"comma-separated, from {', '.join(ALL_MODES)}. The rewrite modes call an LLM",
    )
    modes = [m.strip() for m in parser.parse_args().modes.split(",") if m.strip()]

    s = get_settings()
    embedder = FastEmbedEmbedder(s.embedding_model, s.embedding_dim)
    conn = connect(s.database_url)
    init_schema(conn, s.embedding_dim)  # adds the keyword column to an existing index
    store = ChunkStore(conn)
    if store.count_chunks() == 0:
        raise SystemExit("The index is empty. Run `make ingest` first.")
    # Load the cross-encoder once and share it between the two modes that use it.
    reranker = CrossEncoderReranker(s.reranker_model) if any("rerank" in m for m in modes) else None

    rewriter = None
    if any("rewrite" in m for m in modes):
        from rag.rewrite import ClaudeQueryRewriter

        key = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None
        rewriter = ClaudeQueryRewriter(s.rewriter_model, key)

    golden = json.loads(GOLDEN_SET.read_text())
    runs: dict[str, dict] = {}
    for mode in modes:
        retriever = Retriever(
            store,
            embedder,
            mode,
            reranker if "rerank" in mode else None,
            s.candidate_k,
            s.rrf_k,
            rewriter if "rewrite" in mode else None,
        )
        timings: list[float] = []

        def search(question: str, k: int, retriever=retriever, timings=timings):
            t = time.perf_counter()
            out = retriever.retrieve(question, k)
            timings.append((time.perf_counter() - t) * 1000)
            return out

        results = run(search, golden)
        summary = summarize(results)
        # Latency per question, in milliseconds. p50 = the typical question,
        # max = the slowest one (a user waits for that too).
        latency = {
            "p50_ms": round(statistics.median(timings), 1),
            "max_ms": round(max(timings), 1),
        }
        print(f"\n=== mode: {mode} ===")
        print_report(results, summary)
        runs[mode] = {"summary": summary, "latency": latency, "results": results}

    # --- Compare the modes side by side ---
    base = runs.get("vector")
    print("\n=== comparison (k=5; fixed/broke vs vector) ===")
    print(f"{'mode':<15}{'hit@1':>8}{'hit@5':>8}{'rec@5':>8}{'mrr':>8}{'p50 ms':>9}  fixed / broke")
    for mode, r in runs.items():
        sm, lat = r["summary"], r["latency"]
        d = diff_hits(base["results"], r["results"]) if base and mode != "vector" else None
        change = f"{d['fixed']} / {d['broke']}" if d else ""
        r["vs_vector"] = d
        print(
            f"{mode:<15}{sm['hit@1']:>8.3f}{sm['hit@5']:>8.3f}{sm['recall@5']:>8.3f}"
            f"{sm['mrr']:>8.3f}{lat['p50_ms']:>9.1f}  {change}"
        )

    # Save the run with the settings that produced it. Comparing runs without
    # knowing what changed between them is useless.
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = RESULTS_DIR / f"retrieval-{stamp}.json"
    config = {
        "embedding_model": s.embedding_model,
        "chunk_size": s.chunk_size,
        "chunk_overlap": s.chunk_overlap,
        "docs_version": s.docs_version,
        "candidate_k": s.candidate_k,
        "rrf_k": s.rrf_k,
        "reranker_model": s.reranker_model,
        "rewriter_model": s.rewriter_model if rewriter else None,
    }
    for r in runs.values():
        r["results"] = [asdict(q) for q in r["results"]]
    out.write_text(json.dumps({"config": config, "modes": runs}, indent=2))
    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
