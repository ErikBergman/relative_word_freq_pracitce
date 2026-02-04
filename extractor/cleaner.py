from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup


def extract_text(html_path: Path, start: str, end: str) -> str:
    html = html_path.read_text(encoding="utf-8")
    start_idx = html.find(start)
    end_idx = html.find(end, start_idx if start_idx != -1 else 0)
    if start_idx != -1 and end_idx != -1:
        html = html[start_idx:end_idx]
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(" ")
