from __future__ import annotations

import json
from pathlib import Path


def load_config(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))
