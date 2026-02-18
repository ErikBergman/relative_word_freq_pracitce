from __future__ import annotations

from app_toga import PolishVocabApp


def test_split_sentences_basic() -> None:
    text = "To jest zdanie. A to drugie! Czy to trzecie? Tak."
    got = PolishVocabApp._split_sentences(text)
    assert got == [
        "To jest zdanie.",
        "A to drugie!",
        "Czy to trzecie?",
        "Tak.",
    ]


def test_random_quote_for_word_found() -> None:
    sentences = [
        "Ala ma kota.",
        "Kot lubi mleko.",
        "Pies śpi.",
    ]
    quote = PolishVocabApp._random_quote_for_word("kot", sentences)
    assert quote in {"Ala ma kota.", "Kot lubi mleko."}


def test_random_quote_for_word_missing_returns_blank() -> None:
    sentences = [
        "Ala ma kota.",
        "Pies śpi.",
    ]
    quote = PolishVocabApp._random_quote_for_word("słoń", sentences)
    assert quote == ""


def test_random_quote_for_candidates_uses_inflected_forms() -> None:
    sentences = [
        "Rozumiem wszystko.",
        "Rozumiemy już dużo.",
        "Nic nie słyszę.",
    ]
    quote = PolishVocabApp._random_quote_for_candidates(
        ["rozumiem", "rozumiemy"], sentences
    )
    assert quote in {"Rozumiem wszystko.", "Rozumiemy już dużo."}


def test_random_quote_for_candidates_no_hit_returns_blank() -> None:
    sentences = [
        "Rozumiem wszystko.",
    ]
    quote = PolishVocabApp._random_quote_for_candidates(["słuchać", "słucham"], sentences)
    assert quote == ""


def test_split_sentences_ignores_extra_whitespace() -> None:
    text = "Pierwsze zdanie.   \n\nDrugie zdanie!    Trzecie?"
    got = PolishVocabApp._split_sentences(text)
    assert got == ["Pierwsze zdanie.", "Drugie zdanie!", "Trzecie?"]


def test_random_quote_for_word_is_case_insensitive() -> None:
    sentences = [
        "Kot śpi.",
        "Pies biega.",
    ]
    quote = PolishVocabApp._random_quote_for_word("kot", sentences)
    assert quote == "Kot śpi."


def test_format_preview_text_table_empty_returns_blank() -> None:
    assert PolishVocabApp._format_preview_text_table([]) == ""


def test_format_preview_text_table_keeps_columns_aligned() -> None:
    rendered = PolishVocabApp._format_preview_text_table(
        [
            ("zesłaniec", 7, "7.711"),
            ("kościuszkowski", 2, "6.465"),
            ("zsyłać", 12, "6.534"),
        ]
    )
    lines = rendered.splitlines()
    assert len(lines) == 5
    expected_width = len(lines[0])
    assert all(len(line) == expected_width for line in lines)
    assert lines[0].startswith("Word")
    assert "Count" in lines[0]
    assert lines[0].endswith("Score")
