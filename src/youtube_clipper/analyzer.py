"""
AI Analysis Engine for YouTube Clipper.
Handles subtitle/transcript parsing, content density scoring, hook detection,
best clip window selection, and viral title/hashtag generation.
"""

import re
import os
import tempfile
import sys
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from cortes.log import run_cmd
from youtube_clipper.exceptions import ProcessingError

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
    python_env_bin: Optional[str] = None,
    max_clips: int = 5,
    cookies_file: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Downloads subtitles using yt-dlp, parses VTT transcript, and runs AI analysis
    to recommend the top clips.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        vtt_output_template = os.path.join(tmpdir, "subtitle")
        env_bin = Path(python_env_bin) if python_env_bin else Path(sys.executable).parent
        yt_dlp_bin = str(env_bin / "yt-dlp")
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

        result = run_cmd(cmd, stage="transcribe")

        # Find generated VTT file
        vtt_file = None
        for f in os.listdir(tmpdir):
            if f.endswith(".vtt"):
                vtt_file = os.path.join(tmpdir, f)
                break

        if not vtt_file or not os.path.exists(vtt_file):
            detail = (result.stderr or "").strip()
            detail_lower = detail.lower()
            if "sign in to confirm" in detail_lower or "not a bot" in detail_lower:
                message = "YouTube exigiu autenticação; forneça cookies válidos."
            elif "video unavailable" in detail_lower:
                message = "Vídeo indisponível, privado ou removido."
            else:
                message = "Legendas automáticas não encontradas para o vídeo."
            return {
                "success": False,
                "error": message,
                "detail": detail,
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


class SpeechDensityAnalyzer:
    """Deterministic selection heuristic engine maximizing speech density aligned to scene cuts."""

    MIN_DURATION_MS: int = 20000
    MAX_DURATION_MS: int = 58000

    @classmethod
    def parse_transcript_words(cls, transcript_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract word objects with start_ms and end_ms from transcript data."""
        words: List[Dict[str, Any]] = []
        raw_words = transcript_data.get("words", [])
        if not raw_words and "segments" in transcript_data:
            for seg in transcript_data.get("segments", []):
                seg_words = seg.get("words", [])
                if seg_words:
                    raw_words.extend(seg_words)

        for w in raw_words:
            if not isinstance(w, dict):
                continue
            start_ms = w.get("start_ms")
            if start_ms is None and "start" in w:
                start_ms = int(round(float(w["start"]) * 1000))
            end_ms = w.get("end_ms")
            if end_ms is None and "end" in w:
                end_ms = int(round(float(w["end"]) * 1000))
            if start_ms is not None and end_ms is not None and end_ms > start_ms:
                words.append({
                    "word": w.get("word", ""),
                    "start_ms": int(start_ms),
                    "end_ms": int(end_ms),
                })
        words.sort(key=lambda x: x["start_ms"])
        return words

    @classmethod
    def parse_scene_cuts(cls, scenes_data: Dict[str, Any]) -> List[int]:
        """Extract sorted unique scene cut timestamps in milliseconds."""
        cuts = set(scenes_data.get("cut_timestamps_ms", []))
        scenes_list = scenes_data.get("scenes", []) or scenes_data.get("scene_list", [])
        for sc in scenes_list:
            if "start_ms" in sc:
                cuts.add(int(sc["start_ms"]))
            elif "start_time" in sc:
                cuts.add(int(round(float(sc["start_time"]) * 1000)))
            if "end_ms" in sc:
                cuts.add(int(sc["end_ms"]))
            elif "end_time" in sc:
                cuts.add(int(round(float(sc["end_time"]) * 1000)))
        if "video_duration_sec" in scenes_data:
            cuts.add(int(round(float(scenes_data["video_duration_sec"]) * 1000)))
        if "video_duration_ms" in scenes_data:
            cuts.add(int(scenes_data["video_duration_ms"]))
        cuts.add(0)
        return sorted(list(cuts))

    @classmethod
    def compute_spoken_duration_ms(
        cls, words: List[Dict[str, Any]], start_ms: int, end_ms: int
    ) -> int:
        """Calculate total spoken milliseconds overlapping [start_ms, end_ms]."""
        spoken_ms = 0
        for w in words:
            w_start, w_end = w["start_ms"], w["end_ms"]
            overlap = max(0, min(w_end, end_ms) - max(w_start, start_ms))
            spoken_ms += overlap
        return spoken_ms

    @classmethod
    def format_timestamp_ms(cls, ms: int) -> str:
        """Format millisecond timestamp into HH:MM:SS.mmm string."""
        sec_total = ms / 1000.0
        hours = int(sec_total // 3600)
        minutes = int((sec_total % 3600) // 60)
        seconds = sec_total % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

    @classmethod
    def select_best_clip(
        cls,
        transcript_data: Dict[str, Any],
        scenes_data: Dict[str, Any],
        min_duration_ms: int = 20000,
        max_duration_ms: int = 58000,
    ) -> Dict[str, Any]:
        """Select the densest word-timed window bounded by real scene cuts."""
        # 1. Clamp custom duration parameter overrides strictly within [MIN_DURATION_MS, MAX_DURATION_MS]
        eff_min_dur = max(cls.MIN_DURATION_MS, min(cls.MAX_DURATION_MS, int(min_duration_ms)))
        eff_max_dur = max(cls.MIN_DURATION_MS, min(cls.MAX_DURATION_MS, int(max_duration_ms)))
        if eff_min_dur > eff_max_dur:
            eff_min_dur = eff_max_dur

        words = cls.parse_transcript_words(transcript_data)
        cuts = cls.parse_scene_cuts(scenes_data)
        cuts_set = set(cuts)
        if not words:
            raise ProcessingError(
                "Cannot select clip: word-level transcript timestamps are required"
            )
        if len(cuts_set) < 2:
            raise ProcessingError(
                "Cannot select clip: at least two scene boundaries are required"
            )

        max_video_ms = max(cuts) if cuts else 0
        if "duration" in transcript_data and float(transcript_data["duration"]) > 0:
            max_video_ms = max(max_video_ms, int(round(float(transcript_data["duration"]) * 1000)))
        if words:
            max_video_ms = max(max_video_ms, max(w["end_ms"] for w in words))

        # 2. Rejection for video duration < eff_min_dur (or empty inputs resulting in 0ms)
        if max_video_ms < eff_min_dur:
            raise ProcessingError("Cannot select clip: duration must be between 20.0s and 58.0s")

        candidate_starts = sorted(cuts_set)
        candidate_ends_base = cuts_set

        candidates: List[Dict[str, Any]] = []

        for s in candidate_starts:
            min_e = s + eff_min_dur
            max_e = min(s + eff_max_dur, max_video_ms)
            if min_e > max_video_ms:
                continue

            valid_ends = sorted(
                e for e in candidate_ends_base if min_e <= e <= max_e
            )

            for e in valid_ends:
                dur = e - s
                if not (eff_min_dur <= dur <= eff_max_dur):
                    continue

                spoken_ms = cls.compute_spoken_duration_ms(words, s, e)
                density = spoken_ms / float(dur)
                base_score = round(density * 100.0, 2)

                candidates.append({
                    "schema_version": "1.0.0",
                    "start_ms": s,
                    "end_ms": e,
                    "duration_ms": dur,
                    "start_formatted": cls.format_timestamp_ms(s),
                    "end_formatted": cls.format_timestamp_ms(e),
                    "score": base_score,
                    "scene_aligned": True,
                })

        if not candidates:
            raise ProcessingError(
                "Cannot select clip: no 20.0s-58.0s window exists between scene boundaries"
            )

        # Sort deterministically by (score desc, duration_ms desc, -start_ms desc)
        candidates.sort(key=lambda x: (x["score"], x["duration_ms"], -x["start_ms"]), reverse=True)
        best = candidates[0]

        if not (20000 <= best["duration_ms"] <= 58000):
            raise ProcessingError("Cannot select clip: duration must be between 20.0s and 58.0s")

        return best
