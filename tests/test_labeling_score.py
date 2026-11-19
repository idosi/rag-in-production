"""Step 5: reading human labels strictly and pairing them with the judge. No API."""

import json

import pytest

from rag.evals.labeling_score import LabelError, judge_labels, load_labels, pair_up


def write(tmp_path, data):
    p = tmp_path / "labels.json"
    p.write_text(json.dumps(data))
    return p


def item(faithful=None, answers=None, note=""):
    return {"faithful": faithful, "answers": answers, "note": note}


def test_skips_items_not_labeled_yet(tmp_path):
    p = write(tmp_path, {"q1": item(True, "fully"), "q2": item()})
    assert list(load_labels(p)) == ["q1"]


def test_string_boolean_is_rejected(tmp_path):
    p = write(tmp_path, {"q1": item("true", "fully")})
    with pytest.raises(LabelError, match="q1.*without quotes"):
        load_labels(p)


def test_half_filled_item_is_rejected(tmp_path):
    with pytest.raises(LabelError):
        load_labels(write(tmp_path, {"q1": item(True, None)}))
    with pytest.raises(LabelError):
        load_labels(write(tmp_path, {"q1": item(None, "fully")}))


def test_unknown_answers_value_is_rejected(tmp_path):
    with pytest.raises(LabelError, match="answers"):
        load_labels(write(tmp_path, {"q1": item(True, "full")}))


def verdict(claims, answers):
    return {"unsupported_claims": claims, "answers_question": answers}


def test_judge_labels_maps_claims_to_faithful():
    assert judge_labels({"verdict": verdict([], "fully")}) == {
        "faithful": True,
        "answers": "fully",
    }
    assert judge_labels({"verdict": verdict(["x"], "no")})["faithful"] is False


def test_pair_up_lines_human_and_judge_up_in_id_order():
    labels = {"q2": item(True, "no"), "q1": item(False, "fully")}
    results = [
        {"id": "q1", "verdict": verdict(["c"], "fully")},
        {"id": "q2", "verdict": verdict([], "partially")},
    ]
    pairs = pair_up(labels, results)
    assert [p[0] for p in pairs] == ["q1", "q2"]
    assert pairs[1][1]["answers"] == "no" and pairs[1][2]["answers"] == "partially"


def test_pair_up_rejects_an_id_from_another_run():
    with pytest.raises(LabelError, match="q9"):
        pair_up({"q9": item(True, "fully")}, [{"id": "q1", "verdict": verdict([], "fully")}])
