from __future__ import annotations

from collections import Counter


def top_words(items, limit: int) -> list[tuple[str, int]]:
    if isinstance(items, Counter):
        return items.most_common(limit)
    counts = Counter(items)
    return counts.most_common(limit)
