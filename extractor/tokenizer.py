from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable

from ufal.udpipe import Model, Pipeline


WORD_RE = re.compile(r"[\wąćęłńóśźż]+", re.IGNORECASE)
_UDPIPE_MODEL: Model | None = None
_UDPIPE_PIPELINE: Pipeline | None = None
_LEMMA_CACHE: dict[str, str] = {}
_DEFAULT_MODEL_PATH = Path("data/udpipe/polish-pdb-ud-2.5-191206.udpipe")


def _load_udpipe(model_path: Path | None = None) -> Pipeline:
    global _UDPIPE_MODEL, _UDPIPE_PIPELINE
    if _UDPIPE_PIPELINE is not None:
        return _UDPIPE_PIPELINE
    path = model_path or _DEFAULT_MODEL_PATH
    model = Model.load(str(path))
    if model is None:
        raise RuntimeError(f"Failed to load UDPipe model: {path}")
    _UDPIPE_MODEL = model
    _UDPIPE_PIPELINE = Pipeline(model, "tokenize", Pipeline.DEFAULT, Pipeline.DEFAULT, "conllu")
    return _UDPIPE_PIPELINE


def _feat_case(feats: str) -> str | None:
    if not feats or feats == "_":
        return None
    for part in feats.split("|"):
        if part.startswith("Case="):
            return part.split("=", 1)[1]
    return None


def _iter_udpipe_tokens(
    text: str,
    progress: Callable[[int | None, int], None] | None = None,
) -> list[tuple[str, str, str]]:
    pipeline = _load_udpipe()
    conllu = pipeline.process(text)
    tokens: list[tuple[str, str, str]] = []
    for line in conllu.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        token_id, form, lemma, _upos, _xpos, feats = parts[:6]
        if "-" in token_id or "." in token_id:
            continue
        form_l = form.lower()
        if not WORD_RE.fullmatch(form_l):
            continue
        lemma_l = lemma.lower() if lemma and lemma != "_" else form_l
        tokens.append((form_l, lemma_l, feats))

    if progress is not None:
        progress(len(tokens), 0)
    return tokens


def tokenize(
    text: str,
    progress: Callable[[int | None, int], None] | None = None,
) -> list[str]:
    stream = _iter_udpipe_tokens(text, progress=progress)
    tokens: list[str] = []
    for idx, (form, _lemma, feats) in enumerate(stream):
        if form == "z":
            case = None
            for _nxt_form, _nxt_lemma, nxt_feats in stream[idx + 1 :]:
                case = _feat_case(nxt_feats)
                if case:
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
        tokens.append(form)
        if progress is not None:
            progress(None, 1)
    return tokens


def lemmatize_token(token: str) -> str:
    if token in _LEMMA_CACHE:
        return _LEMMA_CACHE[token]

    if token.startswith("z (") and token.endswith(")"):
        _LEMMA_CACHE[token] = token
        return token

    pipeline = _load_udpipe()
    conllu = pipeline.process(token)
    lemma = token
    for line in conllu.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            lemma = parts[2] or token
            break
    _LEMMA_CACHE[token] = lemma
    return lemma


def lemma_groups(
    tokens: list[str],
    text: str | None = None,
    progress: Callable[[int | None, int], None] | None = None,
) -> dict[str, dict[str, int]]:
    groups: dict[str, dict[str, int]] = {}
    stream = _iter_udpipe_tokens(text or " ".join(tokens), progress=progress)
    for idx, (form, lemma, feats) in enumerate(stream):
        if form == "z":
            case = None
            for _nxt_form, _nxt_lemma, nxt_feats in stream[idx + 1 :]:
                case = _feat_case(nxt_feats)
                if case:
                    break
            if case == "Ins":
                form = lemma = "z (instr.)"
            elif case == "Gen":
                form = lemma = "z (gen.)"
            else:
                form = lemma = "z"
        forms = groups.setdefault(lemma, {})
        forms[form] = forms.get(form, 0) + 1
        if progress is not None:
            progress(None, 1)
    return groups
