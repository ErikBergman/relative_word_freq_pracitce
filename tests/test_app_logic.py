from __future__ import annotations

from collections import Counter

from app_logic import Row, Settings, apply_ignore_patterns, build_rows, render_html


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
