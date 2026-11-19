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


# --------------------------------------------------------------------------
# The report
# --------------------------------------------------------------------------


def axis_stats(pairs: list[tuple[str, dict, dict]], axis: str) -> dict:
    """Agreement numbers for one question ("faithful" or "answers")."""
    from collections import Counter

    from rag.evals.agreement import cohens_kappa, percent_agreement

    human = [h[axis] for _, h, _ in pairs]
    judge = [j[axis] for _, _, j in pairs]
    return {
        "n": len(pairs),
        "agreement": percent_agreement(human, judge),
        "kappa": cohens_kappa(human, judge),
        "counts": Counter(zip(human, judge, strict=True)),  # (human, judge) -> how many
    }


def disagreements(pairs: list[tuple[str, dict, dict]], results: list[dict]) -> list[dict]:
    """Every item where you and the judge differ on either question, with what each side
    said and WHY (the judge's unsupported claims and reasoning, your note). These are the
    items to read: either the judge missed something or you did."""
    by_id = {r["id"]: r for r in results}
    out = []
    for id_, human, judge in pairs:
        if human["faithful"] == judge["faithful"] and human["answers"] == judge["answers"]:
            continue
        r = by_id[id_]
        out.append(
            {
                "id": id_,
                "question": r["question"],
                "human": human,
                "judge": judge,
                "unsupported_claims": r["verdict"]["unsupported_claims"],
                "judge_reasoning": r["verdict"]["reasoning"],
            }
        )
    return out


def interpret(kappa: float) -> str:
    """Landis & Koch (1977), the usual rough scale."""
    for limit, word in ((0.2, "slight"), (0.4, "fair"), (0.6, "moderate"), (0.8, "substantial")):
        if kappa <= limit:
            return word
    return "almost perfect"


def format_report(pairs, results) -> str:
    lines = [f"Compared {len(pairs)} answers: your labels vs the judge.\n"]
    for axis, title in (
        ("faithful", "faithful (no statement outside the sources)"),
        ("answers", "answers the question (fully / partially / no)"),
    ):
        s = axis_stats(pairs, axis)
        lines.append(
            f"{title}\n  agreement {s['agreement']:.0%}   kappa {s['kappa']:.2f} "
            f"({interpret(s['kappa'])})"
        )
        for (h, j), n in sorted(s["counts"].items(), key=lambda kv: str(kv[0])):
            lines.append(f"    you {h!s:<9} judge {j!s:<9} {n}")
        lines.append("")
    diffs = disagreements(pairs, results)
    lines.append(f"{len(diffs)} items where you and the judge differ. Read each one:\n")
    for d in diffs:
        lines.append(
            f"--- {d['id']}: {d['question']}\n"
            f"  you:   faithful={d['human']['faithful']} answers={d['human']['answers']}"
            f"  note: {d['human']['note']}\n"
            f"  judge: faithful={d['judge']['faithful']} answers={d['judge']['answers']}"
        )
        for claim in d["unsupported_claims"]:
            lines.append(f"    judge says unsupported: {claim}")
        lines.append(f"    judge reasoning: {d['judge_reasoning']}\n")
    lines.append(
        "Note: the sample is stratified by the judge's outcome (see labeling.py), so this "
        "measures the judge on these kinds of answers, not the model's overall rate."
    )
    return "\n".join(lines)


def main() -> None:
    import argparse

    from rag.evals.labeling import DEFAULT_MODEL, DEFAULT_RUN, LABELING_DIR

    parser = argparse.ArgumentParser(description="Compare your labels with the judge.")
    parser.add_argument("--labels", type=Path, default=LABELING_DIR / "labels.json")
    parser.add_argument("--run", type=Path, default=DEFAULT_RUN)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    results = json.loads(args.run.read_text())["results"][args.model]
    try:
        labels = load_labels(args.labels)
        if not labels:
            raise SystemExit(f"No finished labels in {args.labels}.")
        pairs = pair_up(labels, results)
    except LabelError as e:
        raise SystemExit(f"labels.json: {e}") from e
    print(format_report(pairs, results))


if __name__ == "__main__":
    main()
