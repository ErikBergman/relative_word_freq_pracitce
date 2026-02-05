from __future__ import annotations

import argparse
from pathlib import Path

from collections import Counter

from extractor import (
    extract_text,
    lemma_groups,
    load_config,
    preload_spacy,
    spacy_cached,
    tokenize,
    top_words,
)
from extractor.frequency import score_words

try:
    from rich.console import Console
    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
    from rich.table import Table
except Exception:  # pragma: no cover - optional dependency
    Progress = None
    Console = None
    Table = None


def _estimate_spacy_load_seconds() -> int:
    return 3 if spacy_cached() else 90


def main() -> None:
    parser = argparse.ArgumentParser(description="Basic Polish vocab extractor")
    parser.add_argument("input", type=Path, help="Path to HTML file")
    parser.add_argument(
        "--config", type=Path, default=Path("config.json"), help="Path to config JSON"
    )
    parser.add_argument("--limit", type=int, default=50, help="Number of top words")
    parser.add_argument(
        "--plain",
        action="store_true",
        help="Use plain top list without wordfreq scoring",
    )
    args = parser.parse_args()

    estimate_seconds = _estimate_spacy_load_seconds()
    preload_spacy(estimate_seconds, show_progress=Progress is not None)

    use_rich = Progress is not None and Console is not None and Table is not None

    if not use_rich:
        config = load_config(args.config)
        start = config["start"]
        end = config["end"]

        text = extract_text(args.input, start, end)
        tokens = tokenize(text)
        groups = lemma_groups(tokens)
    else:
        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
        ) as progress:
            def updater(task_id):
                def _update(total: int | None, advance: int) -> None:
                    if total is not None:
                        progress.update(task_id, total=total)
                    if advance:
                        progress.advance(task_id, advance)
                return _update

            task_clean = progress.add_task("Clean HTML", total=1)
            task_tokenize = progress.add_task("Tokenize", total=1)
            task_lemma = progress.add_task("Lemmatize", total=1)
            task_count = progress.add_task("Count", total=1)

            config = load_config(args.config)
            start = config["start"]
            end = config["end"]

            text = extract_text(args.input, start, end)
            progress.advance(task_clean, 1)

            tokens = tokenize(text, progress=updater(task_tokenize))
            groups = lemma_groups(tokens, progress=updater(task_lemma))
            progress.advance(task_count, 1)

    counts = Counter(tokens)
    for lemma, forms in groups.items():
        if len(forms) > 1:
            counts[f"{lemma}*"] = sum(forms.values())

    if not use_rich:
        if args.plain:
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
        else:
            for word, count, score in score_words(counts, args.limit):
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
                        print(f"{word}\t{count}\t{score:.3f}\t({details})")
                        continue
                print(f"{word}\t{count}\t{score:.3f}")
        return

    console = Console()
    table = Table(show_lines=False)
    table.add_column("Word", overflow="fold")
    table.add_column("Count", justify="right")
    if args.plain:
        table.add_column("Forms", overflow="fold")
        for word, count in top_words(counts, args.limit):
            details = ""
            if word.endswith("*"):
                lemma = word[:-1]
                forms = groups.get(lemma, {})
                details = ", ".join(
                    f"{form} {form_count}"
                    for form, form_count in sorted(
                        forms.items(), key=lambda item: item[1], reverse=True
                    )
                )
            table.add_row(word, str(count), details)
    else:
        table.add_column("Score", justify="right")
        table.add_column("Forms", overflow="fold")
        for word, count, score in score_words(counts, args.limit):
            details = ""
            if word.endswith("*"):
                lemma = word[:-1]
                forms = groups.get(lemma, {})
                details = ", ".join(
                    f"{form} {form_count}"
                    for form, form_count in sorted(
                        forms.items(), key=lambda item: item[1], reverse=True
                    )
                )
            table.add_row(word, str(count), f"{score:.3f}", details)
    console.print(table)


if __name__ == "__main__":
    main()
