from __future__ import annotations

import re

import spacy


WORD_RE = re.compile(r"[\wąćęłńóśźż]+", re.IGNORECASE)
_NLP = None
_LEMMA_CACHE: dict[str, str] = {}


def _load_spacy():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("pl_core_news_sm", disable=["parser", "ner", "senter"])
    return _NLP


def tokenize(text: str) -> list[str]:
    nlp = _load_spacy()
    doc = nlp(text)
    tokens: list[str] = []

    for idx, tok in enumerate(doc):
        token_text = tok.text.lower()
        if not WORD_RE.fullmatch(token_text):
            continue

        if token_text == "z":
            case = None
            for nxt in doc[idx + 1 :]:
                nxt_text = nxt.text.lower()
                if not WORD_RE.fullmatch(nxt_text):
                    continue
                case_val = nxt.morph.get("Case", None)
                if case_val:
                    case = case_val[0]
                break

            if case == "Ins":
                tokens.append("z (instr.)")
            elif case == "Gen":
                tokens.append("z (gen.)")
            else:
                tokens.append("z")
            continue

        tokens.append(token_text)

    return tokens


def lemmatize_token(token: str) -> str:
    if token in _LEMMA_CACHE:
        return _LEMMA_CACHE[token]

    if token.startswith("z (") and token.endswith(")"):
        _LEMMA_CACHE[token] = token
        return token

    nlp = _load_spacy()
    doc = nlp(token)
    lemma = doc[0].lemma_ if doc else token
    _LEMMA_CACHE[token] = lemma
    return lemma


def lemma_groups(tokens: list[str]) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    missing = [
        t
        for t in dict.fromkeys(tokens)
        if t not in _LEMMA_CACHE and not (t.startswith("z (") and t.endswith(")"))
    ]
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
