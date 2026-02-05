from __future__ import annotations

import argparse
from pathlib import Path

from collections import Counter

from extractor import extract_text, lemma_groups, load_config, tokenize, top_words
from extractor.frequency import score_words

try:
    from rich.console import Console
    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn
    from rich.table import Table
except Exception:  # pragma: no cover - optional dependency
    Progress = None
    Console = None
    Table = None




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
    parser.add_argument(
        "--allow-ones",
        action="store_true",
        help="Include words that appear only once",
    )
    parser.add_argument(
        "--allow-inflections-in-list",
        action="store_true",
        help="Include inflected forms in the top list (default shows only lemmas)",
    )
    args = parser.parse_args()

    use_rich = Progress is not None and Console is not None and Table is not None

    if not use_rich:
        config = load_config(args.config)
        start = config["start"]
        end = config["end"]

        text = extract_text(args.input, start, end)
        tokens = tokenize(text)
        groups = lemma_groups(tokens, text=text)
    else:
        with Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
        ) as progress: # type: ignore
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
            groups = lemma_groups(tokens, text=text, progress=updater(task_lemma))
            progress.advance(task_count, 1)

    counts = Counter(tokens)
    if not args.allow_ones:
        counts = Counter({k: v for k, v in counts.items() if v > 1})
    for lemma, forms in groups.items():
        if len(forms) > 1:
            counts[f"{lemma}*"] = sum(forms.values())

    if not use_rich:
        if args.plain:
            if args.allow_inflections_in_list:
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
                lemma_rows = []
                for lemma, forms in groups.items():
                    total = sum(forms.values())
                    if total <= 1 and not args.allow_ones:
                        continue
                    details = ", ".join(
                        f"{form} {form_count}"
                        for form, form_count in sorted(
                            forms.items(), key=lambda item: item[1], reverse=True
                        )
                    )
                    lemma_rows.append((lemma, total, details))
                lemma_rows.sort(key=lambda item: item[1], reverse=True)
                for lemma, total, details in lemma_rows[: args.limit]:
                    if details:
                        print(f"{lemma}\t{total}\t({details})")
                    else:
                        print(f"{lemma}\t{total}")
        else:
            if args.allow_inflections_in_list:
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
            else:
                lemma_counts = Counter(
                    {lemma: sum(forms.values()) for lemma, forms in groups.items()}
                )
                if not args.allow_ones:
                    lemma_counts = Counter(
                        {k: v for k, v in lemma_counts.items() if v > 1}
                    )
                for lemma, total, score in score_words(lemma_counts, args.limit):
                    forms = groups.get(lemma, {})
                    details = ", ".join(
                        f"{form} {form_count}"
                        for form, form_count in sorted(
                            forms.items(), key=lambda item: item[1], reverse=True
                        )
                    )
                    if details:
                        print(f"{lemma}\t{total}\t{score:.3f}\t({details})")
                    else:
                        print(f"{lemma}\t{total}\t{score:.3f}")
        return

    console = Console() # type: ignore
    table = Table(show_lines=False) # type: ignore
    table.add_column("Word", overflow="fold")
    table.add_column("Count", justify="right")
    if args.plain:
        table.add_column("Forms", overflow="fold")
        if args.allow_inflections_in_list:
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
            lemma_rows = []
            for lemma, forms in groups.items():
                total = sum(forms.values())
                if total <= 1 and not args.allow_ones:
                    continue
                details = ", ".join(
                    f"{form} {form_count}"
                    for form, form_count in sorted(
                        forms.items(), key=lambda item: item[1], reverse=True
                    )
                )
                lemma_rows.append((lemma, total, details))
            lemma_rows.sort(key=lambda item: item[1], reverse=True)
            for lemma, total, details in lemma_rows[: args.limit]:
                table.add_row(lemma, str(total), details)
    else:
        table.add_column("Score", justify="right")
        table.add_column("Forms", overflow="fold")
        if args.allow_inflections_in_list:
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
        else:
            lemma_counts = Counter(
                {lemma: sum(forms.values()) for lemma, forms in groups.items()}
            )
            if not args.allow_ones:
                lemma_counts = Counter(
                    {k: v for k, v in lemma_counts.items() if v > 1}
                )
            for lemma, total, score in score_words(lemma_counts, args.limit):
                forms = groups.get(lemma, {})
                details = ", ".join(
                    f"{form} {form_count}"
                    for form, form_count in sorted(
                        forms.items(), key=lambda item: item[1], reverse=True
                    )
                )
                table.add_row(lemma, str(total), f"{score:.3f}", details)
    console.print(table)


if __name__ == "__main__":
    main()
