from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup


WORD_RE = re.compile(r"[\wąćęłńóśźż]+", re.IGNORECASE)


def extract_text(html_path: Path, start: str, end: str) -> str:
    html = html_path.read_text(encoding="utf-8")
    start_idx = html.find(start)
    end_idx = html.find(end, start_idx if start_idx != -1 else 0)
    if start_idx != -1 and end_idx != -1:
        html = html[start_idx:end_idx]
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ")


def top_words(text: str, limit: int) -> list[tuple[str, int]]:
    words = WORD_RE.findall(text.lower())
    counts = Counter(words)
    return counts.most_common(limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Basic Polish vocab extractor")
    parser.add_argument("input", type=Path, help="Path to HTML file")
    parser.add_argument(
        "--config", type=Path, default=Path("config.json"), help="Path to config JSON"
    )
    parser.add_argument("--limit", type=int, default=50, help="Number of top words")
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    start = config["start"]
    end = config["end"]

    text = extract_text(args.input, start, end)
    for word, count in top_words(text, args.limit):
        print(f"{word}\t{count}")


if __name__ == "__main__":
    main()
