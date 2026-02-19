from __future__ import annotations

from collections import Counter

from app_logic import (
    Row,
    Settings,
    append_unique_clozemaster_entries,
    apply_ignore_patterns,
    build_clozemaster_entries,
    build_rows,
    render_html,
    split_sentences,
)


def test_apply_ignore_patterns_supports_wildcards() -> None:
    tokens = ["rp288", "kot", "podkast", "abc123", "kotek"]
    got = apply_ignore_patterns(tokens, (" rp* ", "*123", "kot"))
    assert got == ["podkast", "kotek"]


def test_apply_ignore_patterns_empty_returns_same_list() -> None:
    tokens = ["kot", "pies"]
    got = apply_ignore_patterns(tokens, ())
    assert got is tokens


def test_build_rows_lemma_mode_sorts_forms_and_removes_singletons() -> None:
    counts = Counter({"unused": 1})
    groups = {
        "kot": {"koty": 2, "kota": 3},
        "pies": {"pies": 1},
        "mysz": {"myszy": 2},
    }
    settings = Settings(
        start="x",
        end="y",
        limit=10,
        allow_ones=False,
        allow_inflections=False,
        use_wordfreq=False,
    )
    rows = build_rows(counts, groups, settings)

    assert [row.word for row in rows] == ["kot", "mysz"]
    assert rows[0].count == 5
    assert rows[0].forms == "kota 3, koty 2"
    assert rows[0].score is None


def test_build_rows_inflection_mode_uses_token_counts() -> None:
    counts = Counter({"kot": 4, "pies": 2, "mysz": 1})
    groups = {"kot": {"koty": 4}}
    settings = Settings(
        start="x",
        end="y",
        limit=2,
        allow_ones=False,
        allow_inflections=True,
        use_wordfreq=False,
    )
    rows = build_rows(counts, groups, settings)
    assert [row.word for row in rows] == ["kot", "pies"]
    assert [row.count for row in rows] == [4, 2]
    assert all(row.forms == "" for row in rows)


def test_render_html_formats_score_and_empty_score_cell() -> None:
    rows = [
        Row(word="kot", count=3, score=1.23456, forms="kota 2, koty 1"),
        Row(word="pies", count=2, score=None, forms=""),
    ]
    html = render_html("Demo", rows)
    assert "<title>Demo</title>" in html
    assert "<td class='num'>1.235</td>" in html
    assert "<td class='num'></td>" in html
    assert "<td>kota 2, koty 1</td>" in html


def test_split_sentences_handles_multiple_punctuation() -> None:
    text = "To jest zdanie. To drugie!  A trzecie?  "
    assert split_sentences(text) == ["To jest zdanie.", "To drugie!", "A trzecie?"]


def test_build_clozemaster_entries_uses_literal_form_from_sentence() -> None:
    rows = [Row(word="pieróg", count=2, score=1.0, forms="pierogi 2")]
    groups = {"pieróg": {"pierogi": 2}}
    sentences = [
        "Lubię jeść pierogi z mięsem.",
        "To inny przykład.",
    ]
    entries = build_clozemaster_entries(
        rows,
        groups,
        sentences,
        allow_inflections=False,
    )
    assert entries == [("Lubię jeść pierogi z mięsem.", "", "pierogi", "", "")]


def test_build_clozemaster_entries_preserves_capitalization() -> None:
    rows = [Row(word="pierogi", count=1, score=1.0, forms="")]
    groups: dict[str, dict[str, int]] = {}
    sentences = ["Pierogi są bardzo smaczne."]
    entries = build_clozemaster_entries(
        rows,
        groups,
        sentences,
        allow_inflections=True,
    )
    assert entries == [("Pierogi są bardzo smaczne.", "", "Pierogi", "", "")]


def test_append_unique_clozemaster_entries_deduplicates(tmp_path) -> None:
    csv_path = tmp_path / "clozemaster_input_realpolish.csv"
    entries = [
        ("Pierogi są bardzo smaczne.", "", "Pierogi", "", ""),
        ("Lubię jeść pierogi z mięsem.", "", "pierogi", "", ""),
    ]
    added, skipped = append_unique_clozemaster_entries(csv_path, entries)
    assert (added, skipped) == (2, 0)

    added, skipped = append_unique_clozemaster_entries(csv_path, entries)
    assert (added, skipped) == (0, 2)

    lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2


def test_build_clozemaster_entries_skips_sentences_over_300_chars() -> None:
    rows = [Row(word="pierogi", count=1, score=1.0, forms="")]
    groups: dict[str, dict[str, int]] = {}
    long_sentence = ("pierogi " * 50).strip()  # > 300 chars
    short_sentence = "Pierogi są bardzo smaczne."
    entries = build_clozemaster_entries(
        rows,
        groups,
        [long_sentence, short_sentence],
        allow_inflections=True,
    )
    assert entries == [(short_sentence, "", "Pierogi", "", "")]
