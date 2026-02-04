from __future__ import annotations

from collections import Counter


def top_words(tokens: list[str], limit: int) -> list[tuple[str, int]]:
    counts = Counter(tokens)
    return counts.most_common(limit)
