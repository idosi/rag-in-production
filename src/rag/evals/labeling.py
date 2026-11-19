"""Step 5: label answers by hand, to check the LLM judge.

The judge (Opus) decides, for every answer, whether it is grounded in the sources
and whether it answers the question. All the numbers in the answer evals (2c, 2g)
rest on those verdicts. Nobody has checked the judge, so this step does.

    make labeling-sheet      builds evals/labeling/sheet.md + labels.json (needs the DB, free)
    ... you read the sheet and fill labels.json ...
    make labeling-score      compares your labels with the judge's (see agreement.py)

The sheet is BLIND on purpose: it never shows the judge's verdict or the outcome,
because seeing the judge's opinion first makes a person agree with it.

The sources are retrieved again (the run file stores only the answers). Search is
deterministic, so they match the run as long as the index did not change since.
`retrieval_hit` is recomputed as a check: if it differs from the stored one, the
sources are not the ones the judge saw and the sheet says so.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from rag.evals.retrieval import GOLDEN_SET, RESULTS_DIR, section_key
from rag.generator import format_sources
from rag.models import RetrievedChunk

LABELING_DIR = RESULTS_DIR.parent / "labeling"
DEFAULT_RUN = RESULTS_DIR / "answers-20261109-113323.json"
DEFAULT_MODEL = "ollama:qwen2.5:3b"
# How many answers to take from each judge outcome. Stratified, not random: a random
# sample of 30 would hold almost no "wrong" answers, and we want to see how the judge
# behaves on every kind. The kappa is computed on this sample, so it is a statement
# about the judge on these kinds of answers, not about the model's overall rate.
SAMPLE = {"correct": 11, "unfaithful": 11, "partial": 6, "wrong": 2}


def pick_sample(results: list[dict], per_outcome: dict[str, int], seed: int = 0) -> list[dict]:
    """Take up to N judged answers per outcome, then shuffle so the order gives no hint."""
    rng = random.Random(seed)
    picked: list[dict] = []
    for outcome, n in per_outcome.items():
        pool = sorted(
            (r for r in results if r["outcome"] == outcome and r.get("verdict")),
            key=lambda r: r["id"],
        )
        picked += rng.sample(pool, min(n, len(pool)))
    rng.shuffle(picked)
    return picked


def render_item(n: int, total: int, r: dict, sources: list[RetrievedChunk]) -> str:
    """One answer, with its question and sources, and no trace of the judge's opinion."""
    return (
        f"\n---\n\n## {n}/{total} · {r['id']}\n\n"
        f"**Question:** {r['question']}\n\n"
        f"{format_sources(sources)}\n\n"
        f"**Answer:**\n\n{r['answer']}\n"
    )


INSTRUCTIONS = """\
# Labeling sheet

For every item, open `labels.json` and set two fields under its id:

- `"faithful"`: `true` if EVERY factual statement and every line of code in the answer
  appears in the sources above. `false` if even one statement or code detail is not
  there (also when it is true about FastAPI in general: outside knowledge counts as
  unsupported). Rephrasing a source is fine.
- `"answers"`: `"fully"` (gives what was asked), `"partially"` (helps but leaves out an
  important part the sources contain) or `"no"` (does not answer).

Do it before you look at the judge's results. Be strict and literal, like the judge's
instructions say. Write a short `"note"` when you are unsure, it is useful later.
"""


def build_sheet(
    sample: list[dict], sources_by_id: dict[str, list[RetrievedChunk]], golden: list[dict]
) -> tuple[str, dict, list[str]]:
    """Returns (sheet markdown, labels template, warnings)."""
    relevant = {q["id"]: set(q["relevant"]) for q in golden}
    warnings: list[str] = []
    parts = [INSTRUCTIONS]
    for i, r in enumerate(sample, start=1):
        sources = sources_by_id[r["id"]]
        hit = any(section_key(s) in relevant[r["id"]] for s in sources)
        if hit != r["retrieval_hit"]:
            warnings.append(r["id"])
        parts.append(render_item(i, len(sample), r, sources))
    template = {r["id"]: {"faithful": None, "answers": None, "note": ""} for r in sample}
    return "".join(parts), template, warnings


def main() -> None:
    from rag.config import get_settings
    from rag.db import connect, init_schema
    from rag.embeddings import FastEmbedEmbedder
    from rag.retrieval import build_retriever
    from rag.store import ChunkStore

    parser = argparse.ArgumentParser(description="Build the blind labeling sheet.")
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    out_sheet, out_labels = LABELING_DIR / "sheet.md", LABELING_DIR / "labels.json"
    if out_labels.exists():
        raise SystemExit(
            f"{out_labels} already exists. Move it away first: it may hold your labels."
        )

    run = json.loads(args.run.read_text())
    results = run["results"][args.model]
    golden = json.loads(GOLDEN_SET.read_text())
    sample = pick_sample(results, SAMPLE, args.seed)

    s = get_settings()
    conn = connect(s.database_url.get_secret_value())
    init_schema(conn, s.embedding_dim)
    store = ChunkStore(conn)
    if store.count_chunks() == 0:
        raise SystemExit("The index is empty. Run `make ingest` first.")
    retriever = build_retriever(store, FastEmbedEmbedder(s.embedding_model, s.embedding_dim))
    sources_by_id = {r["id"]: retriever.retrieve(r["question"], s.top_k) for r in sample}

    sheet, template, warnings = build_sheet(sample, sources_by_id, golden)
    LABELING_DIR.mkdir(parents=True, exist_ok=True)
    out_sheet.write_text(sheet)
    out_labels.write_text(json.dumps(template, indent=2, ensure_ascii=False))
    print(f"{len(sample)} answers -> {out_sheet}\nLabels template -> {out_labels}")
    if warnings:
        print(
            "WARNING: for these ids the retrieval differs from the run (the index changed?), "
            f"so the sources may not be the ones the judge saw: {', '.join(warnings)}"
        )


if __name__ == "__main__":
    main()
