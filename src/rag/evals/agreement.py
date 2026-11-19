"""How much do two labelers agree? (Step 5, exercise 5-1, written by Ido.)

    percent_agreement   the share of items where both said the same thing
    cohens_kappa        the same, after removing the agreement you would get by luck

Used by labeling_score.py to compare the human labels with the judge's verdicts.
"""

import math
from collections import Counter


def percent_agreement(a: list, b: list) -> float:
    """Share of positions where a[i] == b[i]. Raise ValueError if the lists differ in
    length or are empty (there is nothing to compare)."""
    if not a or len(a) != len(b):
        raise ValueError("need two non-empty lists of the same length")
    agree = sum(1 for x, y in zip(a, b, strict=True) if x == y)
    return agree / len(a)


def cohens_kappa(a: list, b: list) -> float:
    """Cohen's kappa for two labelers over any hashable labels (True/False, "fully", ...).

        po = percent_agreement(a, b)
        pe = sum over every label L of: (share of a that is L) * (share of b that is L)
        kappa = (po - pe) / (1 - pe)

    pe is the agreement two labelers would reach by luck, given how often each uses
    each label. When pe == 1 both always use one and the same label (so they agree on
    everything) and the formula would divide by zero: there is nothing to measure,
    return 1.0.
    """
    po = percent_agreement(a, b)
    counter_a, counter_b = Counter(a), Counter(b)
    pe = sum(counter_a[label] / len(a) * counter_b[label] / len(b) for label in set(a) | set(b))
    if math.isclose(pe, 1):
        return 1.0
    return (po - pe) / (1 - pe)
