"""Step 5, part 2: compare the human labels with the judge's verdicts.

    make labeling-score

Two questions, both answered by you and by the judge for the same answers:

    faithful   no statement in the answer is missing from the sources
               (judge: `unsupported_claims` is empty)
    answers    "fully" | "partially" | "no"
               (judge: `answers_question`)

This module is the plumbing: read your labels STRICTLY (a typo must fail loudly,
never score as a disagreement), skip the items you have not labeled yet, and line
the two labelers up. The agreement maths is in agreement.py.
"""

from __future__ import annotations

import json
from pathlib import Path

ANSWERS = {"fully", "partially", "no"}


class LabelError(ValueError):
    """A labels.json entry that cannot be trusted."""


def load_labels(path: Path) -> dict[str, dict]:
    """Read labels.json. Returns only the items that are fully labeled.

    An item still holding null is "not done yet" and is skipped, so a half-finished
    file can be scored. Anything else that is not exactly right raises LabelError:
    `"faithful": "true"` (a string, not a boolean) would otherwise compare unequal
    to the judge's True and show up as a disagreement nobody can explain.
    """
    raw = json.loads(path.read_text())
    done: dict[str, dict] = {}
    for id_, item in raw.items():
        faithful, answers = item.get("faithful"), item.get("answers")
        if faithful is None and answers is None:
            continue
        if not isinstance(faithful, bool):
            raise LabelError(
                f"{id_}: faithful must be true or false without quotes, got {faithful!r}"
            )
        if answers not in ANSWERS:
            raise LabelError(
                f'{id_}: answers must be "fully", "partially" or "no", got {answers!r}'
            )
        done[id_] = {"faithful": faithful, "answers": answers, "note": item.get("note", "")}
    return done


def judge_labels(result: dict) -> dict:
    """The judge's verdict on the same two questions."""
    v = result["verdict"]
    return {"faithful": not v["unsupported_claims"], "answers": v["answers_question"]}


def pair_up(labels: dict[str, dict], results: list[dict]) -> list[tuple[str, dict, dict]]:
    """(id, human, judge) for every labeled id, in id order. An id that is not in the
    run (or was never judged) raises: it means labels.json is from a different run."""
    by_id = {r["id"]: r for r in results}
    pairs = []
    for id_ in sorted(labels):
        r = by_id.get(id_)
        if r is None or not r.get("verdict"):
            raise LabelError(f"{id_}: not a judged answer in this run")
        pairs.append((id_, labels[id_], judge_labels(r)))
    return pairs
