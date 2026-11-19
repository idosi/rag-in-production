"""Step 5: the blind labeling sheet. No DB, no API."""

from rag.evals.labeling import build_sheet, pick_sample, render_item
from rag.models import Chunk, RetrievedChunk


def src(anchor):
    return RetrievedChunk(Chunk("d", 0, "h", f"https://x/d/#{anchor}", "the text"), 0.9)


def result(id_, outcome, hit=True):
    return {
        "id": id_,
        "question": f"Question {id_}?",
        "answer": f"Answer {id_}",
        "outcome": outcome,
        "retrieval_hit": hit,
        "verdict": {"reasoning": "SECRET-REASONING", "unsupported_claims": ["SECRET-CLAIM"]},
    }


def test_pick_sample_takes_per_outcome_and_skips_unjudged():
    results = [result(f"a{i}", "correct") for i in range(5)]
    results += [result("b1", "unfaithful"), {**result("b2", "unfaithful"), "verdict": None}]
    picked = pick_sample(results, {"correct": 3, "unfaithful": 5}, seed=1)
    outcomes = sorted(r["outcome"] for r in picked)
    assert outcomes == ["correct", "correct", "correct", "unfaithful"]  # b2 not judged


def test_pick_sample_is_repeatable_for_a_seed():
    results = [result(f"a{i}", "correct") for i in range(20)]
    a = pick_sample(results, {"correct": 5}, seed=7)
    b = pick_sample(results, {"correct": 5}, seed=7)
    assert [r["id"] for r in a] == [r["id"] for r in b]


def test_sheet_is_blind_to_the_judge():
    r = result("q1", "unfaithful")
    sheet, _, _ = build_sheet([r], {"q1": [src("a")]}, [{"id": "q1", "relevant": ["d#a"]}])
    assert "Answer q1" in sheet and "Question q1?" in sheet and "<source" in sheet
    assert "SECRET" not in sheet and "unfaithful" not in sheet


def test_template_has_an_empty_entry_per_answer():
    sample = [result("q1", "correct"), result("q2", "wrong")]
    golden = [{"id": "q1", "relevant": []}, {"id": "q2", "relevant": []}]
    _, template, _ = build_sheet(sample, {"q1": [src("a")], "q2": [src("a")]}, golden)
    assert template == {
        "q1": {"faithful": None, "answers": None, "note": ""},
        "q2": {"faithful": None, "answers": None, "note": ""},
    }


def test_warns_when_retrieval_no_longer_matches_the_run():
    r = result("q1", "correct", hit=True)
    golden = [{"id": "q1", "relevant": ["d#zzz"]}]  # the new sources miss it
    _, _, warnings = build_sheet([r], {"q1": [src("a")]}, golden)
    assert warnings == ["q1"]


def test_render_item_numbers_from_one():
    text = render_item(1, 30, result("q9", "correct"), [src("a")])
    assert "## 1/30 · q9" in text
