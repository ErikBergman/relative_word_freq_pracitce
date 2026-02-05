from __future__ import annotations

import re
from typing import Callable

import spacy


WORD_RE = re.compile(r"[\wąćęłńóśźż]+", re.IGNORECASE)
_NLP = None
_LEMMA_CACHE: dict[str, str] = {}


def _load_spacy():
    global _NLP
    if _NLP is None:
        _NLP = spacy.load("pl_core_news_sm", disable=["parser", "ner", "senter"])
    return _NLP


def spacy_cached() -> bool:
    return _NLP is not None


def preload_spacy(estimate_seconds: int, show_progress: bool = True) -> None:
    if _NLP is not None:
        return

    if not show_progress:
        _load_spacy()
        return

    try:
        from rich.progress import BarColumn, Progress, TimeRemainingColumn
    except Exception:  # pragma: no cover - optional dependency
        _load_spacy()
        return

    import threading
    import time

    done = threading.Event()

    def _load() -> None:
        _load_spacy()
        done.set()

    thread = threading.Thread(target=_load, daemon=True)
    thread.start()

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TimeRemainingColumn(),
    ) as progress:
        task = progress.add_task("Loading spaCy model...", total=estimate_seconds)
        start = time.perf_counter()
        while not done.is_set():
            elapsed = time.perf_counter() - start
            progress.update(task, completed=min(elapsed, estimate_seconds))
            time.sleep(0.1)
        progress.update(task, completed=estimate_seconds)


def tokenize(
    text: str,
    progress: Callable[[int | None, int], None] | None = None,
) -> list[str]:
    nlp = _load_spacy()
    doc = nlp(text)
    tokens: list[str] = []
    if progress is not None:
        progress(len(doc), 0)

    for idx, tok in enumerate(doc):
        token_text = tok.text.lower()
        if not WORD_RE.fullmatch(token_text):
            if progress is not None:
                progress(None, 1)
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
            if progress is not None:
                progress(None, 1)
            continue

        tokens.append(token_text)
        if progress is not None:
            progress(None, 1)

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


def lemma_groups(
    tokens: list[str],
    progress: Callable[[int | None, int], None] | None = None,
) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    missing = [
        t
        for t in dict.fromkeys(tokens)
        if t not in _LEMMA_CACHE and not (t.startswith("z (") and t.endswith(")"))
    ]
    if missing:
        nlp = _load_spacy()
        if progress is not None:
            progress(len(missing), 0)
        for doc in nlp.pipe(missing, batch_size=256):
            token = doc[0].text if doc else ""
            lemma = doc[0].lemma_ if doc else token
            _LEMMA_CACHE[token] = lemma
            if progress is not None:
                progress(None, 1)
    elif progress is not None:
        progress(1, 1)

    for token in tokens:
        lemma = _LEMMA_CACHE.get(token, token)
        forms = groups.setdefault(lemma, {})
        forms[token] = forms.get(token, 0) + 1
    return groups
