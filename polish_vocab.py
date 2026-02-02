from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup


WORD_RE = re.compile(r"[\wąćęłńóśźż]+", re.IGNORECASE)


def extract_text(html_path: Path) -> str:
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ")


def top_words(text: str, limit: int) -> list[tuple[str, int]]:
    words = WORD_RE.findall(text.lower())
    counts = Counter(words)
    return counts.most_common(limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Basic Polish vocab extractor")
    parser.add_argument("input", type=Path, help="Path to HTML file")
    parser.add_argument("--limit", type=int, default=50, help="Number of top words")
    args = parser.parse_args()

    text = extract_text(args.input)
    for word, count in top_words(text, args.limit):
        print(f"{word}\t{count}")


if __name__ == "__main__":
    main()
