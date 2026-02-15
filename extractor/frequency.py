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
    max_global_zipf: float | None = None,
    baseline_total: int | None = None,
) -> list[tuple[str, int, float]]:
    try:
        from wordfreq import zipf_frequency
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "wordfreq is required for score_words(). Install with: pip install wordfreq"
        ) from exc

    total = baseline_total if baseline_total is not None else sum(counts.values())
    total = total or 1
    scored: list[tuple[str, int, float]] = []
    for word, count in counts.items():
        key = word[:-1] if word.endswith("*") else word
        local_zipf = math.log10((count / total) * 1_000_000_000)
        global_zipf = zipf_frequency(key, lang)
        if global_zipf < min_global_zipf:
            continue
        if max_global_zipf is not None and global_zipf > max_global_zipf:
            continue
        score = local_zipf - global_zipf
        scored.append((word, count, score))

    scored.sort(key=lambda item: item[2], reverse=True)
    return scored[:limit]


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
