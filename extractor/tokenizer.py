from __future__ import annotations

import re

import spacy


WORD_RE = re.compile(r"[\wąćęłńóśźż]+", re.IGNORECASE)
_NLP = None
_LEMMA_CACHE: dict[str, str] = {}


def tokenize(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


def _load_spacy():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("pl_core_news_sm", disable=["parser", "ner", "senter"])
    return _NLP


def lemmatize_token(token: str) -> str:
    if token in _LEMMA_CACHE:
        return _LEMMA_CACHE[token]

    nlp = _load_spacy()
    doc = nlp(token)
    lemma = doc[0].lemma_ if doc else token
    _LEMMA_CACHE[token] = lemma
    return lemma


def normalize_tokens(tokens: list[str]) -> list[str]:
    normalized: list[str] = []
    lemma_forms: dict[str, set[str]] = {}
    lemmas: list[str] = []

    for token in tokens:
        lemma = lemmatize_token(token)
        lemmas.append(lemma)
        lemma_forms.setdefault(lemma, set()).add(token)

    for token, lemma in zip(tokens, lemmas):
        normalized.append(token)
        if len(lemma_forms[lemma]) > 1:
            normalized.append(f"{lemma}*")

    return normalized


def lemma_groups(tokens: list[str]) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    missing = [t for t in dict.fromkeys(tokens) if t not in _LEMMA_CACHE]
    if missing:
        nlp = _load_spacy()
        for doc in nlp.pipe(missing, batch_size=256):
            token = doc[0].text if doc else ""
            lemma = doc[0].lemma_ if doc else token
            _LEMMA_CACHE[token] = lemma

    for token in tokens:
        lemma = _LEMMA_CACHE.get(token, token)
        forms = groups.setdefault(lemma, {})
        forms[token] = forms.get(token, 0) + 1
    return groups
