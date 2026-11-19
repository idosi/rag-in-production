"""Exercise 5-1: how much do two labelers agree?

You will compare YOUR labels with the judge's. Two numbers matter:

  percent_agreement   the share of items where both said the same thing
  cohens_kappa        the same, after removing the agreement you would get by luck

Run:   uv run pytest exercises/labeling -q
"""
from collections import Counter
import math

def percent_agreement(a: list, b: list) -> float:
    """Share of positions where a[i] == b[i]. Raise ValueError if the lists differ in
    length or are empty (there is nothing to compare)."""
    if  (not a and not b) | len(a) != len(b):
        raise ValueError
    AgreeNum=0
    total_count=0
    for x,y in zip(a,b):
        if x == y:
            AgreeNum+=1
        total_count+=1

    return AgreeNum/total_count   



def cohens_kappa(a: list, b: list) -> float:
    """Cohen's kappa for two labelers over any hashable labels (True/False, "fully", ...).

        po = percent_agreement(a, b)
        pe = sum over every label L of: (share of a that is L) * (share of b that is L)
        kappa = (po - pe) / (1 - pe)

    pe is the agreement two labelers would reach by luck, given how often each uses
    each label. When pe == 1 (both always use one and the same label) the formula
    divides by zero: return 1.0 if they agree on everything, else 0.0.
    """
    po = percent_agreement(a, b)

    counter_a=Counter(a)   # {True: 4, False: 6}
    counter_b=Counter(b)   # {True: 4, False: 6}


    pe = 0
    for label in set(a) | set(b):
        pe_curr = counter_a[label]/len(a) * counter_b[label]/len(b)
        pe+=pe_curr

    if math.isclose(pe, 1):
        return 1.0
    return (po-pe)/ (1-pe)



