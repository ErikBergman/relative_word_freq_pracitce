from __future__ import annotations

import math
from collections import Counter

from extractor.frequency import blend_scores_from_terms, precompute_score_terms


EPS = 1e-9


def _score_for(
    counts: Counter,
    ref_probs: dict[str, float],
    *,
    a: float,
    word: str,
) -> float:
    terms = precompute_score_terms(counts, ref_probs=ref_probs, eps=EPS)
    scored = dict(
        (w, score)
        for w, _count, score in blend_scores_from_terms(
            terms,
            limit=100,
            balance_a=a,
            min_global_zipf=0.0,
            max_global_zipf=None,
        )
    )
    return scored[word]


def test_a_one_returns_log_tf_plus_one() -> None:
    counts = Counter({"kot": 4, "pies": 2})
    score = _score_for(counts, {"kot": 0.0001, "pies": 0.0002}, a=1.0, word="kot")
    assert math.isclose(score, math.log(5.0), rel_tol=1e-12, abs_tol=1e-12)


def test_a_zero_returns_log_relative_ratio() -> None:
    counts = Counter({"kot": 4, "pies": 2})
    total = 6.0
    p_target = 4.0 / total
    p_ref = 0.01
    score = _score_for(counts, {"kot": p_ref, "pies": 0.02}, a=0.0, word="kot")
    expected = math.log((p_target + EPS) / (p_ref + EPS))
    assert math.isclose(score, expected, rel_tol=1e-12, abs_tol=1e-12)


def test_missing_reference_probability_treated_as_zero() -> None:
    counts = Counter({"rzadkiew": 3})
    score = _score_for(counts, {}, a=0.0, word="rzadkiew")
    expected = math.log((1.0 + EPS) / (0.0 + EPS))
    assert math.isclose(score, expected, rel_tol=1e-12, abs_tol=1e-12)


def test_no_nan_or_inf_for_zero_tf_or_zero_ref() -> None:
    counts = Counter({"zero_tf": 0, "known": 2})
    terms = precompute_score_terms(counts, ref_probs={"known": 0.0, "zero_tf": 0.0}, eps=EPS)
    scored = blend_scores_from_terms(
        terms,
        limit=100,
        balance_a=0.37,
        min_global_zipf=0.0,
        max_global_zipf=None,
    )
    assert scored
    for _word, _count, score in scored:
        assert math.isfinite(score)


def test_balance_a_clamped_above_one() -> None:
    counts = Counter({"kot": 4})
    score = _score_for(counts, {"kot": 0.0001}, a=9.0, word="kot")
    assert math.isclose(score, math.log(5.0), rel_tol=1e-12, abs_tol=1e-12)


def test_balance_a_clamped_below_zero() -> None:
    counts = Counter({"kot": 4})
    total = 4.0
    p_target = 1.0
    p_ref = 0.01
    score = _score_for(counts, {"kot": p_ref}, a=-3.0, word="kot")
    expected = math.log((p_target + EPS) / (p_ref + EPS))
    assert math.isclose(score, expected, rel_tol=1e-12, abs_tol=1e-12)


def test_asterisk_word_uses_reference_without_suffix() -> None:
    counts = Counter({"kot*": 2})
    terms = precompute_score_terms(
        counts,
        ref_probs={"kot": 0.01, "kot*": 0.5},
        eps=EPS,
    )
    expected = math.log(1.0 + EPS) - math.log(0.01 + EPS)
    assert math.isclose(
        terms["kot*"].log_ratio,
        expected,
        rel_tol=1e-12,
        abs_tol=1e-12,
    )


def test_max_zipf_filter_excludes_overly_common_word() -> None:
    counts = Counter({"common": 2, "rare": 2})
    terms = precompute_score_terms(
        counts,
        ref_probs={
            "common": 0.1,     # zipf ~ 8.0
            "rare": 0.000001,  # zipf ~ 3.0
        },
        eps=EPS,
    )
    scored = blend_scores_from_terms(
        terms,
        limit=10,
        balance_a=0.5,
        min_global_zipf=0.0,
        max_global_zipf=5.0,
    )
    assert [word for word, _count, _score in scored] == ["rare"]
