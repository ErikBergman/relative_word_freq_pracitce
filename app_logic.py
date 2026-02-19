from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
import re
from typing import Callable

from extractor.cleaner import extract_text
from extractor.frequency import filter_counts_by_zipf, score_words, top_words
from extractor.tokenizer import lemma_groups, tokenize


ProgressCallback = Callable[[str, int | None, int], None]


@dataclass(frozen=True)
class Settings:
    start: str
    end: str
    limit: int = 50
    allow_ones: bool = False
    allow_inflections: bool = False
    use_wordfreq: bool = True
    min_zipf: float = 1.0
    max_zipf: float = 7.0
    balance_a: float = 0.5
    ignore_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Row:
    word: str
    count: int
    score: float | None
    forms: str


def build_rows(
    counts: Counter,
    groups: dict[str, dict[str, int]],
    settings: Settings,
) -> list[Row]:
    rows: list[Row] = []

    if settings.allow_inflections:
        baseline_total = sum(counts.values())
        if settings.use_wordfreq:
            counts = filter_counts_by_zipf(
                counts,
                min_global_zipf=settings.min_zipf,
                max_global_zipf=settings.max_zipf,
            )
            for word, count, score in score_words(
                counts,
                settings.limit,
                min_global_zipf=settings.min_zipf,
                max_global_zipf=settings.max_zipf,
                baseline_total=baseline_total,
                balance_a=settings.balance_a,
            ):
                rows.append(Row(word, count, score, ""))
        else:
            for word, count in top_words(counts, settings.limit):
                rows.append(Row(word, count, None, ""))
        return rows

    lemma_counts = Counter({lemma: sum(forms.values()) for lemma, forms in groups.items()})
    if not settings.allow_ones:
        lemma_counts = Counter({k: v for k, v in lemma_counts.items() if v > 1})
    baseline_total = sum(lemma_counts.values())

    if settings.use_wordfreq:
        lemma_counts = filter_counts_by_zipf(
            lemma_counts,
            min_global_zipf=settings.min_zipf,
            max_global_zipf=settings.max_zipf,
        )
        items = score_words(
            lemma_counts,
            settings.limit,
            min_global_zipf=settings.min_zipf,
            max_global_zipf=settings.max_zipf,
            baseline_total=baseline_total,
            balance_a=settings.balance_a,
        )
        for lemma, total, score in items:
            forms = groups.get(lemma, {})
            details = ", ".join(
                f"{form} {form_count}"
                for form, form_count in sorted(
                    forms.items(), key=lambda item: item[1], reverse=True
                )
            )
            rows.append(Row(lemma, total, score, details))
    else:
        items = top_words(lemma_counts, settings.limit)
        for lemma, total in items:
            forms = groups.get(lemma, {})
            details = ", ".join(
                f"{form} {form_count}"
                for form, form_count in sorted(
                    forms.items(), key=lambda item: item[1], reverse=True
                )
            )
            rows.append(Row(lemma, total, None, details))

    return rows


def process_file(
    path: Path,
    settings: Settings,
    progress: ProgressCallback | None = None,
) -> list[Row]:
    def report(step: str, total: int | None, advance: int) -> None:
        if progress is not None:
            progress(step, total, advance)

    report("clean", 1, 0)
    text = extract_text(path, settings.start, settings.end)
    report("clean", None, 1)

    tokens = tokenize(text, progress=lambda t, a: report("tokenize", t, a))
    tokens = apply_ignore_patterns(tokens, settings.ignore_patterns)
    groups = lemma_groups(tokens, text=None, progress=lambda t, a: report("lemmatize", t, a))

    counts = Counter(tokens)
    if not settings.allow_ones:
        counts = Counter({k: v for k, v in counts.items() if v > 1})

    report("count", 1, 1)
    return build_rows(counts, groups, settings)


def apply_ignore_patterns(
    tokens: list[str],
    patterns: tuple[str, ...] | list[str],
) -> list[str]:
    normalized_patterns = tuple(p.strip().lower() for p in patterns if p.strip())
    if not normalized_patterns:
        return tokens
    return [
        token
        for token in tokens
        if not any(fnmatch(token, pattern) for pattern in normalized_patterns)
    ]


def render_html(title: str, rows: list[Row]) -> str:
    headers = ["Word", "Count", "Score", "Forms"]
    lines = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'/>",
        f"<title>{title}</title>",
        "<style>",
        "body{font-family:system-ui, sans-serif; padding:20px;}",
        "table{border-collapse:collapse; width:100%;}",
        "th,td{border:1px solid #ddd; padding:6px 8px; font-size:14px;}",
        "th{background:#f5f5f5; text-align:left;}",
        "td.num{text-align:right; white-space:nowrap;}",
        "</style></head><body>",
        f"<h1>{title}</h1>",
        "<table><thead><tr>",
    ]
    lines += [f"<th>{h}</th>" for h in headers]
    lines += ["</tr></thead><tbody>"]
    for r in rows:
        score = "" if r.score is None else f"{r.score:.3f}"
        lines.append(
            "<tr>"
            f"<td>{r.word}</td>"
            f"<td class='num'>{r.count}</td>"
            f"<td class='num'>{score}</td>"
            f"<td>{r.forms}</td>"
            "</tr>"
        )
    lines += ["</tbody></table></body></html>"]
    return "\n".join(lines)


def split_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?<=[.!?])\s+", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def _first_word_match(sentence: str, candidates: list[str]) -> str:
    for candidate in candidates:
        pattern = re.compile(rf"\b{re.escape(candidate)}\b", re.IGNORECASE)
        match = pattern.search(sentence)
        if match:
            return match.group(0)
    return ""


def build_clozemaster_entries(
    rows: list[Row],
    groups: dict[str, dict[str, int]],
    sentences: list[str],
    *,
    allow_inflections: bool,
) -> list[tuple[str, str, str, str, str]]:
    entries: list[tuple[str, str, str, str, str]] = []
    if not sentences:
        return entries

    for row in rows:
        if allow_inflections:
            candidates = [row.word]
        else:
            forms = groups.get(row.word, {})
            sorted_forms = [
                form
                for form, _count in sorted(
                    forms.items(), key=lambda item: item[1], reverse=True
                )
            ]
            candidates = sorted_forms or [row.word]

        selected_sentence = ""
        selected_word = ""
        for sentence in sentences:
            if len(sentence) > 300:
                continue
            literal = _first_word_match(sentence, candidates)
            if literal:
                selected_sentence = sentence
                selected_word = literal
                break

        if not selected_sentence:
            continue

        entries.append((selected_sentence, "", selected_word, "", ""))

    return entries


def append_unique_clozemaster_entries(
    csv_path: Path,
    entries: list[tuple[str, str, str, str, str]],
) -> tuple[int, int]:
    if not entries:
        return (0, 0)

    existing: set[tuple[str, str, str, str, str]] = set()
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, delimiter=";")
            for row in reader:
                if len(row) >= 5:
                    existing.add((row[0], row[1], row[2], row[3], row[4]))

    added = 0
    skipped = 0
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        for entry in entries:
            if entry in existing:
                skipped += 1
                continue
            writer.writerow(entry)
            existing.add(entry)
            added += 1

    return (added, skipped)
