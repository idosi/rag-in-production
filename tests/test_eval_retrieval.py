import json
from pathlib import Path

import pytest

from rag.evals.retrieval import GOLDEN_SET, run, score_question, section_key, summarize
from rag.models import Chunk, RetrievedChunk


def hit(doc, anchor, score=0.5):
    url = f"https://fastapi.tiangolo.com/{doc}/#{anchor}"
    return RetrievedChunk(Chunk(doc, 0, "h", url, "text"), score)


def test_section_key_uses_document_and_anchor():
    assert section_key(hit("tutorial/body", "request-body")) == "tutorial/body#request-body"


def test_score_question_matches_docstring_example():
    q = {"id": "x", "category": "direct", "question": "?", "relevant": ["d#a", "d#b"]}
    retrieved = [hit("d", "x"), hit("d", "a"), hit("d", "a"), hit("d", "y"), hit("d", "b")]
    r = score_question(q, retrieved)
    assert r.first_hit_rank == 2
    assert (r.hit[1], r.hit[3]) == (False, True)
    assert (r.recall[3], r.recall[5]) == (0.5, 1.0)


def test_summary_mrr_counts_misses_as_zero():
    q1 = {"id": "1", "category": "c", "question": "?", "relevant": ["d#a"]}
    q2 = {"id": "2", "category": "c", "question": "?", "relevant": ["d#z"]}
    results = [score_question(q1, [hit("d", "a")]), score_question(q2, [hit("d", "a")])]
    s = summarize(results)
    assert s["hit@1"] == 0.5
    assert s["mrr"] == 0.5  # (1/1 + 0) / 2


def test_run_skips_unanswerable_questions():
    golden = [
        {"id": "1", "category": "c", "question": "a?", "relevant": ["d#a"]},
        {"id": "u", "category": "unanswerable", "question": "b?", "relevant": []},
    ]
    results = run(lambda question, k: [hit("d", "a")], golden)
    assert [r.id for r in results] == ["1"]


def test_golden_set_is_well_formed():
    golden = json.loads(GOLDEN_SET.read_text())
    ids = [q["id"] for q in golden]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for q in golden:
        assert q["question"].strip()
        assert (q["category"] == "unanswerable") == (q["relevant"] == [])


@pytest.mark.skipif(not Path("data/raw").exists(), reason="docs not downloaded (make ingest)")
def test_golden_set_labels_exist_in_corpus():
    """Every labelled section must exist; catches typos and docs-version drift."""
    from rag.config import get_settings
    from rag.ingest.chunker import split_sections
    from rag.ingest.loader import load_documents

    s = get_settings()
    docs = load_documents(s.docs_version, s.docs_cache_dir)
    valid = {f"{d.id}#{sec.anchor}" for d in docs for sec in split_sections(d.text)}
    golden = json.loads(GOLDEN_SET.read_text())
    missing = [(q["id"], r) for q in golden for r in q["relevant"] if r not in valid]
    assert not missing


def test_diff_hits_lists_fixed_and_broken_questions():
    from rag.evals.retrieval import diff_hits

    qa = {"id": "a", "category": "c", "question": "?", "relevant": ["d#a"]}
    qb = {"id": "b", "category": "c", "question": "?", "relevant": ["d#b"]}
    base = [score_question(qa, [hit("d", "x")]), score_question(qb, [hit("d", "b")])]
    other = [score_question(qa, [hit("d", "a")]), score_question(qb, [hit("d", "x")])]
    assert diff_hits(base, other) == {"fixed": ["a"], "broke": ["b"]}
