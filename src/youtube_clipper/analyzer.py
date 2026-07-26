"""
AI Analysis Engine for YouTube Clipper.
Handles subtitle/transcript parsing, content density scoring, hook detection,
best clip window selection, and viral title/hashtag generation.
"""

import re
import os
import tempfile
import subprocess
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass
class ClipSuggestion:
    rank: int
    start_time: float
    end_time: float
    duration: float
    score: float
    title: str
    summary: str
    transcript: str
    hashtags: List[str]
    start_timestamp: str
    end_timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def seconds_to_timestamp(seconds: float) -> str:
    """Format seconds into HH:MM:SS string."""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class VTTParser:
    """Parses WebVTT subtitle files into structured transcript segments."""

    @staticmethod
    def clean_vtt_text(text: str) -> str:
        """Remove WebVTT inline formatting and timestamps tags."""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"align:\S+|position:\S+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def parse_timestamp(ts_str: str) -> float:
        """Parse HH:MM:SS.mmm or MM:SS.mmm into float seconds."""
        parts = ts_str.strip().split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(parts[0])

    @classmethod
    def parse_vtt_content(cls, vtt_content: str) -> List[TranscriptSegment]:
        """Parse raw WebVTT content string into a deduplicated list of TranscriptSegments."""
        lines = vtt_content.splitlines()
        segments: List[TranscriptSegment] = []
        i = 0

        timestamp_pattern = re.compile(
            r"(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})"
        )

        seen_texts = set()

        while i < len(lines):
            line = lines[i].strip()
            match = timestamp_pattern.search(line)
            if match:
                start_ts = cls.parse_timestamp(match.group(1))
                end_ts = cls.parse_timestamp(match.group(2))

                i += 1
                text_lines = []
                while i < len(lines) and lines[i].strip() and not timestamp_pattern.search(lines[i]):
                    cleaned = cls.clean_vtt_text(lines[i])
                    if cleaned:
                        text_lines.append(cleaned)
                    i += 1

                full_text = " ".join(text_lines).strip()

                if full_text and full_text not in seen_texts:
                    seen_texts.add(full_text)
                    segments.append(TranscriptSegment(start=start_ts, end=end_ts, text=full_text))
            else:
                i += 1

        return segments


class VideoContentAnalyzer:
    """Analyzes transcript segments to detect key moments, hooks, and score clip candidates."""

    HOOK_WORDS = {
        "você sabia", "olha só", "incrível", "segredo", "primeiro", "descobriu", "aconteceu",
        "nunca", "curioso", "verdade", "motivo", "por que", "como", "veja", "atenção", "urgente",
        "surpreendente", "mistério", "história", "resultado", "revelado", "jamais", "entenda"
    }

    QUESTION_WORDS = {"por que", "como", "qual", "quem", "onde", "quando", "quanto", "será"}

    @classmethod
    def score_window(cls, window_segments: List[TranscriptSegment], duration: float) -> float:
        """Calculates engagement score (0-100) for a transcript window."""
        if not window_segments or duration <= 0:
            return 0.0

        full_text = " ".join(s.text for s in window_segments).lower()
        word_count = len(full_text.split())

        # 1. Speech Density Score (words per second) - ideal is 2.0 to 3.5 wps
        wps = word_count / duration
        if 1.5 <= wps <= 4.0:
            density_score = 30.0
        elif wps > 0.5:
            density_score = 15.0
        else:
            density_score = 5.0

        # 2. Hook & Curiosity Keywords
        hook_count = sum(1 for hw in cls.HOOK_WORDS if hw in full_text)
        hook_score = min(35.0, hook_count * 12.0)

        # 3. Question / Engagement
        has_question = "?" in full_text or any(qw in full_text for qw in cls.QUESTION_WORDS)
        question_score = 15.0 if has_question else 0.0

        # 4. Length Penalty/Bonus (ideal clip is 30s to 55s)
        if 30 <= duration <= 55:
            length_score = 20.0
        elif 20 <= duration <= 60:
            length_score = 15.0
        else:
            length_score = 10.0

        total = density_score + hook_score + question_score + length_score
        return round(min(100.0, total), 1)

    @classmethod
    def generate_clip_title(cls, text: str) -> str:
        """Derives a catchy viral title from the clip transcript."""
        clean = re.sub(r"[^\w\s\n]", "", text).strip()
        words = clean.split()
        if not words:
            return "Corte Destaque Viral"
        
        # Take first 4-7 words as base title
        title_base = " ".join(words[:6]).title()
        if len(title_base) > 50:
            title_base = title_base[:47] + "..."
        return title_base

    @classmethod
    def generate_hashtags(cls, text: str) -> List[str]:
        """Generates relevant hashtags for Shorts/Reels."""
        base_tags = ["#shorts", "#viral", "#corte", "#curiosidades"]
        text_lower = text.lower()
        if "história" in text_lower or "anos" in text_lower:
            base_tags.append("#historia")
        if "tecnologia" in text_lower or "ia" in text_lower or "computador" in text_lower:
            base_tags.append("#tecnologia")
        if "segredo" in text_lower or "misterio" in text_lower:
            base_tags.append("#mistério")
        return base_tags[:5]

    @classmethod
    def find_best_clips(
        cls,
        segments: List[TranscriptSegment],
        max_clips: int = 5,
        min_duration: float = 25.0,
        max_duration: float = 55.0,
        overlap_threshold: float = 15.0
    ) -> List[ClipSuggestion]:
        """Finds top N non-overlapping video clips based on AI engagement scoring."""
        if not segments:
            return []

        candidates = []
        n = len(segments)

        for i in range(n):
            current_duration = 0.0
            window = []
            for j in range(i, n):
                seg = segments[j]
                window.append(seg)
                current_duration = seg.end - segments[i].start

                if min_duration <= current_duration <= max_duration:
                    score = cls.score_window(window, current_duration)
                    candidates.append((score, segments[i].start, seg.end, current_duration, window))
                elif current_duration > max_duration:
                    break

        # Sort candidates by highest score
        candidates.sort(key=lambda x: x[0], reverse=True)

        selected: List[ClipSuggestion] = []
        for score, start, end, dur, window in candidates:
            # Check overlap with already selected clips
            is_overlapping = any(
                max(start, sel.start_time) < min(end, sel.end_time) - overlap_threshold
                for sel in selected
            )
            if not is_overlapping:
                transcript_text = " ".join(s.text for s in window)
                title = cls.generate_clip_title(transcript_text)
                hashtags = cls.generate_hashtags(transcript_text)
                summary = f"Momento com alta densidade de fala ({len(transcript_text.split())} palavras) e pontuação de engajamento de {score}/100."

                clip = ClipSuggestion(
                    rank=len(selected) + 1,
                    start_time=round(start, 2),
                    end_time=round(end, 2),
                    duration=round(dur, 2),
                    score=score,
                    title=title,
                    summary=summary,
                    transcript=transcript_text,
                    hashtags=hashtags,
                    start_timestamp=seconds_to_timestamp(start),
                    end_timestamp=seconds_to_timestamp(end)
                )
                selected.append(clip)

                if len(selected) >= max_clips:
                    break

        return selected


def extract_transcript_and_analyze(
    url_or_file: str,
    python_env_bin: str = ".venv/bin",
    max_clips: int = 5,
    cookies_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Downloads subtitles using yt-dlp, parses VTT transcript, and runs AI analysis
    to recommend the top clips.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        vtt_output_template = os.path.join(tmpdir, "subtitle")
        yt_dlp_bin = os.path.join(python_env_bin, "yt-dlp")
        if not os.path.exists(yt_dlp_bin):
            yt_dlp_bin = "yt-dlp"

        effective_cookies = cookies_file or os.environ.get("YOUTUBE_COOKIES_FILE")

        # 1. Download auto-subtitles
        cmd = [
            yt_dlp_bin,
            "--write-auto-subs",
            "--sub-lang", "pt,en",
            "--skip-download",
            "--convert-subs", "vtt",
            "-o", vtt_output_template,
        ]

        if effective_cookies:
            if effective_cookies.lower() in ("chrome", "firefox", "brave", "edge", "safari", "opera"):
                cmd.extend(["--cookies-from-browser", effective_cookies.lower()])
            else:
                cmd.extend(["--cookies", effective_cookies])

        cmd.append(url_or_file)

        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

        # Find generated VTT file
        vtt_file = None
        for f in os.listdir(tmpdir):
            if f.endswith(".vtt"):
                vtt_file = os.path.join(tmpdir, f)
                break

        if not vtt_file or not os.path.exists(vtt_file):
            return {
                "success": False,
                "error": "Legendas automáticas não encontradas para o vídeo.",
                "clips": []
            }

        with open(vtt_file, "r", encoding="utf-8", errors="ignore") as f:
            vtt_content = f.read()

        segments = VTTParser.parse_vtt_content(vtt_content)
        clips = VideoContentAnalyzer.find_best_clips(segments, max_clips=max_clips)

        return {
            "success": True,
            "total_segments": len(segments),
            "clips": [c.to_dict() for c in clips]
        }
