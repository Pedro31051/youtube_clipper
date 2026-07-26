"""Unit tests for youtube_clipper.analyzer module."""

import pytest
from youtube_clipper.analyzer import (
    VTTParser,
    VideoContentAnalyzer,
    TranscriptSegment,
    seconds_to_timestamp
)


def test_seconds_to_timestamp():
    assert seconds_to_timestamp(65) == "01:05"
    assert seconds_to_timestamp(3665) == "01:01:05"
    assert seconds_to_timestamp(0) == "00:00"


def test_vtt_parser_clean_text():
    raw = "Los<00:00:00.359><c> Angeles,</c><00:00:00.799><c> Califórnia.</c>"
    cleaned = VTTParser.clean_vtt_text(raw)
    assert cleaned == "Los Angeles, Califórnia."


def test_vtt_parser_timestamps():
    assert VTTParser.parse_timestamp("00:01:30.500") == 90.5
    assert VTTParser.parse_timestamp("02:15.100") == 135.1


def test_find_best_clips():
    segments = [
        TranscriptSegment(start=0.0, end=10.0, text="Você sabia que este é um segredo incrível sobre o universo?"),
        TranscriptSegment(start=10.0, end=20.0, text="Como isto aconteceu exatamente em 1992 no apartamento em silêncio?"),
        TranscriptSegment(start=20.0, end=35.0, text="A história revela detalhes surpreendentes que jamais foram contados antes.")
    ]

    clips = VideoContentAnalyzer.find_best_clips(segments, max_clips=2, min_duration=10.0, max_duration=40.0)
    assert len(clips) > 0
    top_clip = clips[0]
    assert top_clip.score > 0
    assert "00:00" in top_clip.start_timestamp
    assert len(top_clip.hashtags) > 0


def test_extract_transcript_and_analyze_cookies(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from youtube_clipper.analyzer import extract_transcript_and_analyze

    captured_cmds = []

    def mock_run(cmd, **kwargs):
        captured_cmds.append(cmd)
        # Create a dummy vtt file in tempdir if needed
        # search for -o argument
        if "-o" in cmd:
            idx = cmd.index("-o")
            prefix = cmd[idx + 1]
            with open(f"{prefix}.pt.vtt", "w") as f:
                f.write("WEBVTT\n\n00:00.000 --> 00:05.000\nTest transcript line.\n")
        class DummyRes:
            returncode = 0
            stdout = b""
            stderr = b""
        return DummyRes()

    monkeypatch.setattr("subprocess.run", mock_run)

    # Test with cookies_file parameter
    res = extract_transcript_and_analyze("https://www.youtube.com/watch?v=dQw4w9WgXcQ", cookies_file="/path/to/cookies.txt")
    assert res["success"] is True
    assert "--cookies" in captured_cmds[0]
    assert "/path/to/cookies.txt" in captured_cmds[0]

    # Test with browser name
    captured_cmds.clear()
    res2 = extract_transcript_and_analyze("https://www.youtube.com/watch?v=dQw4w9WgXcQ", cookies_file="chrome")
    assert res2["success"] is True
    assert "--cookies-from-browser" in captured_cmds[0]
    assert "chrome" in captured_cmds[0]

