from __future__ import annotations

import re


WORD_RE = re.compile(r"[\wąćęłńóśźż]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())
