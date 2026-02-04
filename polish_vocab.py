from __future__ import annotations

import argparse
from pathlib import Path

from collections import Counter

from extractor import extract_text, lemma_groups, load_config, tokenize, top_words


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
    groups = lemma_groups(tokens)

    counts = Counter(tokens)
    for lemma, forms in groups.items():
        if len(forms) > 1:
            counts[f"{lemma}*"] = sum(forms.values())

    for word, count in top_words(counts, args.limit):
        if word.endswith("*"):
            lemma = word[:-1]
            forms = groups.get(lemma, {})
            details = ", ".join(
                f"{form} {form_count}"
                for form, form_count in sorted(
                    forms.items(), key=lambda item: item[1], reverse=True
                )
            )
            if details:
                print(f"{word}\t{count}\t({details})")
                continue
        print(f"{word}\t{count}")


if __name__ == "__main__":
    main()
