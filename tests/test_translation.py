from __future__ import annotations

from app_logic import apply_translations_to_clozemaster_entries


class _FakeTranslator:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def translate_many(self, sentences: list[str]) -> list[str]:
        self.calls.append(list(sentences))
        return [f"EN::{s}" for s in sentences]


def test_apply_translations_fills_english_column_and_preserves_other_fields() -> None:
    entries = [
        ("Pierogi są bardzo smaczne.", "", "Pierogi", "", ""),
        ("Lubię jeść pierogi z mięsem.", "", "pierogi", "", ""),
    ]
    translator = _FakeTranslator()

    got = apply_translations_to_clozemaster_entries(entries, translator)

    assert translator.calls == [
        ["Pierogi są bardzo smaczne.", "Lubię jeść pierogi z mięsem."]
    ]
    assert got == [
        (
            "Pierogi są bardzo smaczne.",
            "EN::Pierogi są bardzo smaczne.",
            "Pierogi",
            "",
            "",
        ),
        (
            "Lubię jeść pierogi z mięsem.",
            "EN::Lubię jeść pierogi z mięsem.",
            "pierogi",
            "",
            "",
        ),
    ]


def test_apply_translations_deduplicates_source_sentences_before_translate_call() -> None:
    entries = [
        ("To jest zdanie.", "", "To", "", ""),
        ("To jest zdanie.", "", "zdanie", "", ""),
        ("Drugie zdanie.", "", "Drugie", "", ""),
    ]
    translator = _FakeTranslator()

    got = apply_translations_to_clozemaster_entries(entries, translator)

    assert translator.calls == [["To jest zdanie.", "Drugie zdanie."]]
    assert got[0][1] == "EN::To jest zdanie."
    assert got[1][1] == "EN::To jest zdanie."
    assert got[2][1] == "EN::Drugie zdanie."


def test_apply_translations_empty_input_is_noop() -> None:
    translator = _FakeTranslator()
    assert apply_translations_to_clozemaster_entries([], translator) == []
    assert translator.calls == []

