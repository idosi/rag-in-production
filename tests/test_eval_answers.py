"""Step 2c: answer-eval scoring. No API calls: the generator and judge are faked."""

from rag.evals.answers import (
    AnswerResult,
    Verdict,
    answer_one,
    classify,
    cost_usd,
    judge_one,
    summarize_answers,
)
from rag.generator import NOT_FOUND
from rag.models import Answer, Chunk, RetrievedChunk

ANSWERABLE = {"id": "q1", "category": "direct", "question": "How?", "relevant": ["d#a"]}
UNANSWERABLE = {"id": "u1", "category": "unanswerable", "question": "K8s?", "relevant": []}


def src(anchor):
    return RetrievedChunk(Chunk("d", 0, "h", f"https://x/d/#{anchor}", "text"), 0.9)


class FixedGenerator:
    def __init__(self, text):
        self.text = text

    def generate(self, question, sources):
        cited = [1] if "[1]" in self.text else []
        usage = {"model": "claude-haiku-5-5", "input_tokens": 2000, "output_tokens": 400}
        return Answer(self.text, sources, cited, usage)


class FixedJudge:
    def __init__(self, **verdict):
        self.verdict = Verdict(
            reasoning="r",
            **{"unsupported_claims": [], "answers_question": "fully", "bad_citations": []}
            | verdict,
        )
        self.calls = 0

    def judge(self, question, sources, answer):
        self.calls += 1
        return self.verdict, {
            "model": "claude-opus-5-5",
            "input_tokens": 1000,
            "output_tokens": 100,
        }


def run_one(q, sources, text, judge):
    r = answer_one(q, sources, FixedGenerator(text), "claude-haiku-5-5")
    judge_one(r, q, sources, judge)
    return r


def test_cost_uses_model_prices():
    # Haiku 5.5: $0.10 in / $0.50 out per 1M tokens
    usage = {"model": "claude-haiku-5-5", "input_tokens": 2000, "output_tokens": 400}
    assert cost_usd(usage) == (2000 * 0.10 + 400 * 0.50) / 1_000_000
    assert cost_usd({"model": "unknown", "input_tokens": 9, "output_tokens": 9}) == 0.0


def test_correct_grounded_answer():
    r = run_one(ANSWERABLE, [src("a")], "Use X [1].", FixedJudge())
    assert (r.retrieval_hit, r.refused, r.outcome) == (True, False, "correct")


def test_any_unsupported_claim_makes_the_answer_unfaithful():
    r = run_one(ANSWERABLE, [src("a")], "Use X [1].", FixedJudge(unsupported_claims=["Y"]))
    assert r.outcome == "unfaithful"


def test_refusals_are_not_sent_to_the_judge():
    judge = FixedJudge()
    r = run_one(ANSWERABLE, [src("a")], NOT_FOUND, judge)
    assert judge.calls == 0
    assert r.outcome == "false_refusal"  # the right section WAS in the sources


def test_refusal_is_justified_when_retrieval_missed():
    r = run_one(ANSWERABLE, [src("other")], NOT_FOUND, FixedJudge())
    assert r.outcome == "justified_refusal"


def test_unanswerable_question_must_be_refused():
    assert run_one(UNANSWERABLE, [src("a")], NOT_FOUND, FixedJudge()).outcome == "correct_refusal"
    assert run_one(UNANSWERABLE, [src("a")], "Use kubectl [1].", FixedJudge()).outcome == (
        "hallucinated"
    )


def test_phantom_citations_are_caught():
    r = run_one(ANSWERABLE, [src("a")], "Use X [1][7].", FixedJudge())
    assert r.phantom_citations == [7]  # only 1 source was given


def test_failed_judgement_does_not_crash_the_run():
    class BrokenJudge:
        def judge(self, *a):
            raise RuntimeError("boom")

    r = run_one(ANSWERABLE, [src("a")], "Use X [1].", BrokenJudge())
    assert r.outcome == "not_judged" and "boom" in r.notes[0]


def test_summary_rates_and_denominators():
    rs = [
        run_one(ANSWERABLE, [src("a")], "Use X [1].", FixedJudge()),
        run_one(
            ANSWERABLE | {"id": "q2"}, [src("a")], "Use Z.", FixedJudge(unsupported_claims=["Z"])
        ),
        run_one(UNANSWERABLE, [src("a")], NOT_FOUND, FixedJudge()),
    ]
    s = summarize_answers(rs)
    assert s["correct"] == 0.5  # 1 of 2 answerable
    assert s["unfaithful"] == 0.5  # 1 of 2 judged answers
    assert s["uncited"] == 0.5  # "Use Z." has no [n]
    assert s["correct_refusals"] == "1/1"


def test_classify_partial_and_wrong():
    v = {"unsupported_claims": [], "answers_question": "partially", "bad_citations": []}
    assert classify(ANSWERABLE, True, False, v) == "partial"
    assert classify(ANSWERABLE, True, False, v | {"answers_question": "no"}) == "wrong"


def test_answer_result_is_serialisable():
    import json
    from dataclasses import asdict

    r = run_one(ANSWERABLE, [src("a")], "Use X [1].", FixedJudge())
    assert isinstance(r, AnswerResult)
    json.dumps(asdict(r))
