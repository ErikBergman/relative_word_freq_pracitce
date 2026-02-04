from __future__ import annotations

import argparse
from pathlib import Path

from extractor import extract_text, load_config, tokenize, top_words


def main() -> None:
    parser = argparse.ArgumentParser(description="Basic Polish vocab extractor")
    parser.add_argument("input", type=Path, help="Path to HTML file")
    parser.add_argument(
        "--config", type=Path, default=Path("config.json"), help="Path to config JSON"
    )
    parser.add_argument("--limit", type=int, default=50, help="Number of top words")
    args = parser.parse_args()

    config = load_config(args.config)
    start = config["start"]
    end = config["end"]

    text = extract_text(args.input, start, end)
    tokens = tokenize(text)
    for word, count in top_words(tokens, args.limit):
        print(f"{word}\t{count}")


if __name__ == "__main__":
    main()
