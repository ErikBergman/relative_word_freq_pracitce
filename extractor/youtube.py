from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


_TIMESTAMP_RE = re.compile(
    r"^\s*\d{2}:\d{2}:\d{2}\.\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}\.\d{3}"
)
_TAG_RE = re.compile(r"<[^>]+>")


def fetch_youtube_caption_text(
    url: str,
    languages: tuple[str, ...] = ("pl", "pl-PL", "en"),
) -> str:
    if not shutil.which("yt-dlp"):
        raise RuntimeError("yt-dlp is not installed or not on PATH")

    with TemporaryDirectory(prefix="yt_caps_") as tmp:
        out_tpl = str(Path(tmp) / "%(id)s.%(ext)s")
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-subs",
            "--write-subs",
            "--sub-langs",
            ",".join(languages),
            "--sub-format",
            "vtt",
            "--output",
            out_tpl,
            url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "unknown error").strip()
            raise RuntimeError(f"yt-dlp failed: {msg}")

        vtt_files = sorted(Path(tmp).glob("*.vtt"))
        if not vtt_files:
            return ""

        best = _pick_best_vtt(vtt_files)
        return vtt_to_text(best.read_text(encoding="utf-8", errors="ignore"))


def _pick_best_vtt(files: list[Path]) -> Path:
    def rank(path: Path) -> tuple[int, int]:
        name = path.name.lower()
        lang_score = 0
        if ".pl." in name:
            lang_score = 3
        elif ".pl-" in name:
            lang_score = 2
        elif ".en." in name:
            lang_score = 1
        return (lang_score, path.stat().st_size)

    return sorted(files, key=rank, reverse=True)[0]


def vtt_to_text(vtt: str) -> str:
    lines: list[str] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "WEBVTT":
            continue
        if line.startswith("NOTE"):
            continue
        if _TIMESTAMP_RE.match(line):
            continue
        if line.isdigit():
            continue
        clean = _TAG_RE.sub("", line).strip()
        if clean:
            lines.append(clean)

    # Remove immediate repeats common in auto-captions.
    deduped: list[str] = []
    for chunk in lines:
        if deduped and deduped[-1] == chunk:
            continue
        deduped.append(chunk)
    return " ".join(deduped)

