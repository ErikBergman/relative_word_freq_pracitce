from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import spacy


WORD_RE = re.compile(r"[\wąćęłńóśźż]+", re.IGNORECASE)
_NLP = None
_LEMMA_CACHE: dict[str, str] = {}
_SPACY_CACHE_DIR = Path(".cache/spacy_pl_core_news_sm")


def _load_spacy():
    global _NLP
    if _NLP is None:
        if _SPACY_CACHE_DIR.exists():
            _NLP = spacy.load(_SPACY_CACHE_DIR, disable=["parser", "ner", "senter"])
        else:
            _NLP = spacy.load("pl_core_news_sm", disable=["parser", "ner", "senter"])
            try:
                _SPACY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                _NLP.to_disk(_SPACY_CACHE_DIR)
            except Exception:
                pass
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
    return [form for form, _lemma in _iter_spacy_tokens(text, progress=progress)]


def _iter_spacy_tokens(
    text: str,
    progress: Callable[[int | None, int], None] | None = None,
) -> list[tuple[str, str]]:
    nlp = _load_spacy()
    doc = nlp(text)
    pairs: list[tuple[str, str]] = []
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
                form = "z (instr.)"
            elif case == "Gen":
                form = "z (gen.)"
            else:
                form = "z"
            pairs.append((form, form))
            if progress is not None:
                progress(None, 1)
            continue

        lemma = _normalize_lemma(token_text, tok.lemma_.lower())
        pairs.append((token_text, lemma))
        if progress is not None:
            progress(None, 1)

    return pairs


def _normalize_lemma(token_text: str, lemma: str) -> str:
    if token_text.startswith("z (") and token_text.endswith(")"):
        return token_text

    candidates: list[str] = []
    if lemma.endswith("t"):
        candidates.append(lemma[:-1] + "ć")
    if lemma.endswith("c") and not lemma.endswith("cz"):
        candidates.append(lemma[:-1] + "ć")
    if lemma.endswith("nić"):
        candidates.append(lemma[:-3] + "nieć")
    if lemma.endswith("dzić"):
        candidates.append(lemma[:-3] + "dzieć")
    if lemma.endswith("zić"):
        candidates.append(lemma[:-3] + "zieć")

    try:
        from wordfreq import zipf_frequency
    except Exception:
        return candidates[0] if candidates else lemma

    best = lemma
    best_score = zipf_frequency(lemma, "pl")
    token_score = zipf_frequency(token_text, "pl")

    candidates.extend(_candidates_from_token(token_text))

    min_improvement = 0.0 if lemma == token_text else 0.5
    for cand in candidates:
        score = zipf_frequency(cand, "pl")
        if score > best_score + min_improvement:
            best = cand
            best_score = score

    if best_score == 0 and token_score > 0:
        return token_text

    return best


def _candidates_from_token(token_text: str) -> list[str]:
    endings = {
        "cie": ["ć", "eć", "ieć", "ać", "ić", "yć"],
        "emy": ["eć", "ieć", "ać", "ić", "yć"],
        "amy": ["ać", "eć", "ieć", "ić", "yć"],
        "isz": ["ić", "ieć", "eć"],
        "ysz": ["yć", "ieć", "eć"],
        "esz": ["eć", "ieć", "ać"],
        "asz": ["ać", "ieć", "eć"],
        "ę": ["ać", "eć", "ieć", "ić", "yć"],
        "am": ["ać", "eć", "ieć", "ić", "yć"],
        "em": ["eć", "ieć", "ać"],
        "im": ["ić", "ieć", "eć"],
        "a": ["ać"],
        "e": ["eć", "ieć"],
        "i": ["ić", "ieć"],
        "y": ["yć"],
    }

    candidates: set[str] = set()
    for ending, suffixes in endings.items():
        if token_text.endswith(ending) and len(token_text) > len(ending) + 1:
            stem = token_text[: -len(ending)]
            for suffix in suffixes:
                candidates.add(stem + suffix)
            if stem.endswith("aj"):
                candidates.add(stem[:-2] + "awać")
    return list(candidates)


def lemmatize_token(token: str) -> str:
    if token in _LEMMA_CACHE:
        return _LEMMA_CACHE[token]

    if token.startswith("z (") and token.endswith(")"):
        _LEMMA_CACHE[token] = token
        return token

    nlp = _load_spacy()
    doc = nlp(token)
    raw = doc[0].lemma_ if doc else token
    lemma = _normalize_lemma(token, raw.lower())
    _LEMMA_CACHE[token] = lemma
    return lemma


def lemma_groups(
    tokens: list[str],
    text: str | None = None,
    progress: Callable[[int | None, int], None] | None = None,
) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    if text is not None:
        for form, lemma in _iter_spacy_tokens(text, progress=progress):
            forms = groups.setdefault(lemma, {})
            forms[form] = forms.get(form, 0) + 1
        return groups

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
