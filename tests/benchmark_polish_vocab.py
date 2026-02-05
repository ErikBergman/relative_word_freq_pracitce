from __future__ import annotations

import json
import os
import statistics as stats
import subprocess
import sys
import time
from importlib import import_module
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "polish_vocab.py"
INPUT = HERE / "data" / "RP286.html"


IMPORTS = [
    "argparse",
    "pathlib",
    "collections",
    "extractor",
]


def time_imports() -> dict[str, float]:
    timings: dict[str, float] = {}
    for name in IMPORTS:
        start = time.perf_counter()
        import_module(name)
        timings[name] = time.perf_counter() - start
    try:
        start = time.perf_counter()
        import_module("rich.progress")
        timings["rich.progress"] = time.perf_counter() - start
    except Exception:
        timings["rich.progress"] = -1.0
    return timings


def time_main() -> float:
    import polish_vocab

    argv = [
        str(SCRIPT),
        str(INPUT),
        "--limit",
        "5",
    ]
    old_argv = sys.argv
    sys.argv = argv
    try:
        start = time.perf_counter()
        polish_vocab.main()
        return time.perf_counter() - start
    finally:
        sys.argv = old_argv


def child_run() -> None:
    import io
    from contextlib import redirect_stdout

    timings = time_imports()
    with redirect_stdout(io.StringIO()):
        main_time = time_main()
    payload = {
        "imports": timings,
        "main": main_time,
    }
    print(json.dumps(payload))


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "max": max(values),
        "avg": stats.mean(values),
    }


def parent_run(runs: int) -> None:
    results = []
    for _ in range(runs):
        proc = subprocess.run(
            [sys.executable, __file__, "--child"],
            check=True,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
        results.append(json.loads(proc.stdout.strip()))

    import_names = sorted({k for r in results for k in r["imports"].keys()})
    import_summaries: dict[str, dict[str, float]] = {}
    for name in import_names:
        vals = [r["imports"].get(name, -1.0) for r in results]
        import_summaries[name] = summarize(vals)

    main_vals = [r["main"] for r in results]
    summary = {
        "runs": runs,
        "imports": import_summaries,
        "main": summarize(main_vals),
    }
    print(json.dumps(summary, indent=2))


def main() -> None:
    if "--child" in sys.argv:
        child_run()
        return
    parent_run(5)


if __name__ == "__main__":
    main()
