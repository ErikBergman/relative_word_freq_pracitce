from __future__ import annotations

from collections import Counter
import math


def top_words(items, limit: int) -> list[tuple[str, int]]:
    if isinstance(items, Counter):
        return items.most_common(limit)
    counts = Counter(items)
    return counts.most_common(limit)


def score_words(
    counts: Counter,
    limit: int,
    *,
    lang: str = "pl",
    min_global_zipf: float = 1.0,
) -> list[tuple[str, int, float]]:
    try:
        from wordfreq import zipf_frequency
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "wordfreq is required for score_words(). Install with: pip install wordfreq"
        ) from exc

    total = sum(counts.values()) or 1
    scored: list[tuple[str, int, float]] = []
    for word, count in counts.items():
        key = word[:-1] if word.endswith("*") else word
        local_zipf = math.log10((count / total) * 1_000_000_000)
        global_zipf = zipf_frequency(key, lang)
        if global_zipf < min_global_zipf:
            continue
        score = local_zipf - global_zipf
        scored.append((word, count, score))

    scored.sort(key=lambda item: item[2], reverse=True)
    return scored[:limit]


def filter_counts_by_zipf(
    counts: Counter,
    *,
    min_global_zipf: float = 1.0,
    lang: str = "pl",
) -> Counter:
    try:
        from wordfreq import zipf_frequency
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "wordfreq is required for zipf filtering. Install with: pip install wordfreq"
        ) from exc

    return Counter(
        {
            word: count
            for word, count in counts.items()
            if zipf_frequency(word[:-1] if word.endswith("*") else word, lang)
            >= min_global_zipf
        }
    )
