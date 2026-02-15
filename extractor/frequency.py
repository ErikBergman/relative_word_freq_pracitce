from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from typing import Mapping


def top_words(items, limit: int) -> list[tuple[str, int]]:
    if isinstance(items, Counter):
        return items.most_common(limit)
    counts = Counter(items)
    return counts.most_common(limit)


@dataclass(frozen=True)
class ScoreTerms:
    count: int
    log_tf1: float
    log_ratio: float
    ref_zipf: float


def precompute_score_terms(
    counts: Counter,
    *,
    lang: str = "pl",
    eps: float = 1e-9,
    baseline_total: int | None = None,
    ref_probs: Mapping[str, float] | None = None,
) -> dict[str, ScoreTerms]:
    if ref_probs is None:
        try:
            from wordfreq import word_frequency, zipf_frequency
        except Exception as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "wordfreq is required for score calculations. Install with: pip install wordfreq"
            ) from exc
        get_ref_prob = lambda w: float(word_frequency(w, lang))
        get_ref_zipf = lambda w: float(zipf_frequency(w, lang))
    else:
        def get_ref_prob(w: str) -> float:
            return float(ref_probs.get(w, 0.0))

        def get_ref_zipf(w: str) -> float:
            p = float(ref_probs.get(w, 0.0))
            return math.log10(p * 1_000_000_000) if p > 0 else 0.0

    total = baseline_total if baseline_total is not None else sum(counts.values())
    total = total or 1
    terms: dict[str, ScoreTerms] = {}
    for word, count in counts.items():
        key = word[:-1] if word.endswith("*") else word
        tf = max(float(count), 0.0)
        p_target = tf / float(total)
        p_ref = max(get_ref_prob(key), 0.0)
        log_tf1 = math.log(tf + 1.0)
        log_ratio = math.log(p_target + eps) - math.log(p_ref + eps)
        terms[word] = ScoreTerms(
            count=int(count),
            log_tf1=log_tf1,
            log_ratio=log_ratio,
            ref_zipf=get_ref_zipf(key),
        )
    return terms


def blend_scores_from_terms(
    terms: dict[str, ScoreTerms],
    *,
    limit: int,
    balance_a: float = 0.5,
    min_global_zipf: float = 1.0,
    max_global_zipf: float | None = None,
) -> list[tuple[str, int, float]]:
    a = min(1.0, max(0.0, float(balance_a)))
    scored: list[tuple[str, int, float]] = []
    for word, item in terms.items():
        if item.ref_zipf < min_global_zipf:
            continue
        if max_global_zipf is not None and item.ref_zipf > max_global_zipf:
            continue
        # Blended score: absolute signal (log(tf+1)) + relative signal (target/reference).
        # A relative component near 0 means target and reference probabilities are similar.
        score = a * item.log_tf1 + (1.0 - a) * item.log_ratio
        if not math.isfinite(score):
            continue
        scored.append((word, item.count, score))
    scored.sort(key=lambda row: row[2], reverse=True)
    return scored[:limit]


def score_words(
    counts: Counter,
    limit: int,
    *,
    lang: str = "pl",
    min_global_zipf: float = 1.0,
    max_global_zipf: float | None = None,
    baseline_total: int | None = None,
    balance_a: float = 0.5,
    eps: float = 1e-9,
) -> list[tuple[str, int, float]]:
    terms = precompute_score_terms(
        counts,
        lang=lang,
        eps=eps,
        baseline_total=baseline_total,
    )
    return blend_scores_from_terms(
        terms,
        limit=limit,
        balance_a=balance_a,
        min_global_zipf=min_global_zipf,
        max_global_zipf=max_global_zipf,
    )


def filter_counts_by_zipf(
    counts: Counter,
    *,
    min_global_zipf: float = 1.0,
    max_global_zipf: float | None = None,
    lang: str = "pl",
) -> Counter:
    try:
        from wordfreq import zipf_frequency
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "wordfreq is required for zipf filtering. Install with: pip install wordfreq"
        ) from exc

    filtered: Counter = Counter()
    for word, count in counts.items():
        key = word[:-1] if word.endswith("*") else word
        zipf = zipf_frequency(key, lang)
        if zipf < min_global_zipf:
            continue
        if max_global_zipf is not None and zipf > max_global_zipf:
            continue
        filtered[word] = count
    return filtered
