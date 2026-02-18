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
