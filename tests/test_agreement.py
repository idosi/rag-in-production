"""Agreement metrics (exercise 5-1, written by Ido)."""

import pytest

from rag.evals.agreement import cohens_kappa, percent_agreement

# 10 items. a says True for the first 4. b agrees on 8 of 10 (differs at index 3 and 9).
A = [True, True, True, True, False, False, False, False, False, False]
B = [True, True, True, False, False, False, False, False, False, True]


def test_1_percent_agreement_basic():
    assert percent_agreement(A, B) == pytest.approx(0.8)


def test_2_percent_agreement_perfect_and_none():
    assert percent_agreement([1, 2, 3], [1, 2, 3]) == 1.0
    assert percent_agreement([1, 2, 3], [3, 1, 2]) == 0.0


def test_3_percent_agreement_rejects_bad_input():
    with pytest.raises(ValueError):
        percent_agreement([1, 2], [1])
    with pytest.raises(ValueError):
        percent_agreement([], [])


def test_4_kappa_known_example():
    # po = 0.8; pe = 0.4*0.4 + 0.6*0.6 = 0.52; kappa = 0.28 / 0.48
    assert cohens_kappa(A, B) == pytest.approx(0.5833, abs=1e-3)


def test_5_kappa_perfect_agreement_is_one():
    assert cohens_kappa(A, A) == pytest.approx(1.0)


def test_6_kappa_works_with_more_than_two_labels():
    a = ["fully", "fully", "partially", "no", "partially", "fully"]
    b = ["fully", "partially", "partially", "no", "fully", "fully"]
    # po = 4/6; a: fully 3/6, partially 2/6, no 1/6; b: fully 3/6, partially 2/6, no 1/6
    # pe = (9 + 4 + 1) / 36 = 14/36; kappa = (4/6 - 14/36) / (1 - 14/36)
    assert cohens_kappa(a, b) == pytest.approx((4 / 6 - 14 / 36) / (1 - 14 / 36))


def test_7_kappa_can_be_zero_or_negative_when_agreement_is_only_luck():
    a = [True, True, False, False]
    b = [True, False, True, False]  # agree on 2 of 4, exactly what luck gives
    assert cohens_kappa(a, b) == pytest.approx(0.0)
    assert cohens_kappa([True, False], [False, True]) < 0


def test_8_kappa_when_both_always_say_the_same_label():
    # pe == 1: the formula would divide by zero
    assert cohens_kappa([True, True, True], [True, True, True]) == 1.0
    assert cohens_kappa(["x", "x"], ["x", "x"]) == 1.0


def test_9_kappa_rejects_bad_input():
    with pytest.raises(ValueError):
        cohens_kappa([True], [True, False])
