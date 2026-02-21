from __future__ import annotations

from extractor.youtube import vtt_to_text


def test_vtt_to_text_removes_timestamps_and_tags() -> None:
    vtt = """WEBVTT

00:00:00.000 --> 00:00:01.200
<c>Witam wszystkich.</c>

00:00:01.200 --> 00:00:03.000
To jest test.
"""
    assert vtt_to_text(vtt) == "Witam wszystkich. To jest test."


def test_vtt_to_text_removes_immediate_duplicates() -> None:
    vtt = """WEBVTT

00:00:00.000 --> 00:00:01.000
Cześć

00:00:01.000 --> 00:00:02.000
Cześć

00:00:02.000 --> 00:00:03.000
Świecie
"""
    assert vtt_to_text(vtt) == "Cześć Świecie"

