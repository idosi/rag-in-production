"""Exercise 5-1: how much do two labelers agree?

You will compare YOUR labels with the judge's. Two numbers matter:

  percent_agreement   the share of items where both said the same thing
  cohens_kappa        the same, after removing the agreement you would get by luck

Run:   uv run pytest exercises/labeling -q
"""


def percent_agreement(a: list, b: list) -> float:
    """Share of positions where a[i] == b[i]. Raise ValueError if the lists differ in
    length or are empty (there is nothing to compare)."""
    raise NotImplementedError


def cohens_kappa(a: list, b: list) -> float:
    """Cohen's kappa for two labelers over any hashable labels (True/False, "fully", ...).

        po = percent_agreement(a, b)
        pe = sum over every label L of: (share of a that is L) * (share of b that is L)
        kappa = (po - pe) / (1 - pe)

    pe is the agreement two labelers would reach by luck, given how often each uses
    each label. When pe == 1 (both always use one and the same label) the formula
    divides by zero: return 1.0 if they agree on everything, else 0.0.
    """
    raise NotImplementedError
