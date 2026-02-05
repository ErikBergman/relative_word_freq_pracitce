from __future__ import annotations

from pathlib import Path

import re

from bs4 import BeautifulSoup


def extract_text(html_path: Path, start: str, end: str) -> str:
    html = html_path.read_text(encoding="utf-8")
    start_idx = html.find(start)
    end_idx = html.find(end, start_idx if start_idx != -1 else 0)

    if start_idx == -1 and "[NUMBER]" in start:
        pattern = re.escape(start).replace(r"\[NUMBER\]", r"\d+")
        match = re.search(pattern, html)
        if match:
            start_idx = match.start()
            end_idx = html.find(end, start_idx)

    if start_idx != -1 and end_idx != -1:
        html = html[start_idx:end_idx]

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(
        ["script", "style", "nav", "footer", "header", "aside", "form", "iframe"]
    ):
        tag.decompose()

    for tag in soup.find_all(
        class_=re.compile(
            r"(nav|menu|sidebar|footer|header|widget|breadcrumb|logo|share|social)",
            re.IGNORECASE,
        )
    ):
        tag.decompose()

    content = (
        soup.find("article")
        or soup.find(class_=re.compile(r"entry-content", re.IGNORECASE))
        or soup.find("main")
        or soup
    )

    return content.get_text(" ")
