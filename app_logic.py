from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from extractor.cleaner import extract_text
from extractor.frequency import score_words, top_words
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
        if settings.use_wordfreq:
            for word, count, score in score_words(counts, settings.limit):
                rows.append(Row(word, count, score, ""))
        else:
            for word, count in top_words(counts, settings.limit):
                rows.append(Row(word, count, None, ""))
        return rows

    lemma_counts = Counter({lemma: sum(forms.values()) for lemma, forms in groups.items()})
    if not settings.allow_ones:
        lemma_counts = Counter({k: v for k, v in lemma_counts.items() if v > 1})

    if settings.use_wordfreq:
        items = score_words(lemma_counts, settings.limit)
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
    groups = lemma_groups(tokens, text=text, progress=lambda t, a: report("lemmatize", t, a))

    counts = Counter(tokens)
    if not settings.allow_ones:
        counts = Counter({k: v for k, v in counts.items() if v > 1})

    report("count", 1, 1)
    return build_rows(counts, groups, settings)


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
