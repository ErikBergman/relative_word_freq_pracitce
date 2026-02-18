from __future__ import annotations

from pathlib import Path
from typing import Iterable


def iter_paths_from_drop(*args) -> Iterable[Path]:
    if not args:
        return []
    # Toga may pass (widget, path, x, y) or (widget, paths)
    for item in args:
        if isinstance(item, (list, tuple)):
            return [Path(p) for p in item]
        if isinstance(item, str):
            return [Path(item)]
    return []


def coerce_path(value) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        return Path(value)
    # Toga may return path-like dialog objects.
    maybe_path = getattr(value, "path", None)
    if isinstance(maybe_path, str):
        return Path(maybe_path)
    try:
        return Path(str(value))
    except Exception:
        return None
