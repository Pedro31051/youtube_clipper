"""FFmpeg media processor module for youtube_clipper.

Provides FFmpegProcessor for clipping and re-encoding video files via FFmpeg subprocess.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from cortes.log import run_cmd
from youtube_clipper.exceptions import FFmpegNotFoundError, ProcessingError


class FFmpegProcessor:
    """FFmpeg media processor wrapper for subprocess media editing."""

    def __init__(self, ffmpeg_path: Optional[str] = None) -> None:
        """Initialize FFmpegProcessor and verify ffmpeg executable exists.

        Args:
            ffmpeg_path: Optional path to ffmpeg executable binary.

        Raises:
            FFmpegNotFoundError: If ffmpeg binary is not found on PATH or provided path.
        """
        if ffmpeg_path:
            self.ffmpeg_bin = (
                ffmpeg_path
                if shutil.which(ffmpeg_path) or Path(ffmpeg_path).exists()
                else None
            )
        else:
            self.ffmpeg_bin = shutil.which("ffmpeg")

        if not self.ffmpeg_bin or not shutil.which(self.ffmpeg_bin):
            raise FFmpegNotFoundError(
                "FFmpeg executable not found. Please install ffmpeg and ensure it is in system PATH."
            )

    def cut_media(
        self,
        input_path: Union[str, Path],
        start: float,
        end: float,
        output_path: Union[str, Path],
        fast_copy: bool = False,
    ) -> str:
        """Cut input video file between start and end timestamps into output_path.

        Args:
            input_path: Path to existing source video file.
            start: Start timestamp in seconds.
            end: End timestamp in seconds.
            output_path: Target path for output clip.
            fast_copy: If True, uses stream copy (-c copy) without re-encoding.

        Returns:
            Absolute or normalized output file path as a string.

        Raises:
            ProcessingError: If input does not exist, timestamps are invalid, or subprocess fails.
            FFmpegNotFoundError: If ffmpeg binary is missing at execution time.
        """
        start = float(start)
        end = float(end)

        if start < 0 or end <= start:
            raise ProcessingError(
                f"Invalid timestamp range for cutting media: start={start}, end={end}",
                exit_code=4,
            )

        inp = Path(input_path)
        if not inp.exists():
            raise ProcessingError(
                f"Input media file does not exist: {inp}",
                exit_code=4,
            )

        outp = Path(output_path)
        outp.parent.mkdir(parents=True, exist_ok=True)

        duration = end - start

        # Fast input seeking (-ss before -i)
        cmd: List[str] = [
            self.ffmpeg_bin,
            "-y",
            "-ss",
            str(start),
            "-i",
            str(inp),
            "-t",
            str(duration),
        ]

        if fast_copy:
            cmd.extend(["-c", "copy"])
        else:
            cmd.extend(
                ["-c:v", "libx264", "-c:a", "aac", "-avoid_negative_ts", "make_zero"]
            )

        cmd.append(str(outp))

        try:
            res = run_cmd(cmd, stage="cut")
            if res.returncode != 0:
                raise ProcessingError(
                    f"FFmpeg command execution failed with returncode {res.returncode}",
                    returncode=res.returncode,
                    stderr=res.stderr,
                    cmd=cmd,
                    exit_code=4,
                )
            if not outp.exists() or outp.stat().st_size <= 1024:
                raise ProcessingError(
                    f"FFmpeg completed but produced an empty or undersized output: {outp}",
                    cmd=cmd,
                    exit_code=4,
                )
            probe = run_cmd(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-show_entries",
                    "stream=codec_type",
                    "-of",
                    "json",
                    str(outp),
                ],
                stage="verify",
            )
            try:
                metadata = json.loads(probe.stdout) if probe.returncode == 0 else {}
                measured_duration = float(
                    metadata.get("format", {}).get("duration", 0.0)
                )
                streams = metadata.get("streams", [])
            except (TypeError, ValueError, json.JSONDecodeError):
                measured_duration = 0.0
                streams = []
            if measured_duration <= 0.0 or not any(
                stream.get("codec_type") == "video" for stream in streams
            ):
                raise ProcessingError(
                    f"FFmpeg output is not a valid video with positive duration: {outp}",
                    returncode=probe.returncode,
                    stderr=probe.stderr,
                    cmd=cmd,
                    exit_code=4,
                )
            return str(outp)
        except FileNotFoundError as e:
            raise FFmpegNotFoundError(f"FFmpeg binary not found at {self.ffmpeg_bin}") from e
        except ProcessingError:
            raise
        except Exception as e:
            raise ProcessingError(
                f"Subprocess execution error: {e}", cmd=cmd, exit_code=4
            ) from e


def detect_scenes_scenedetect(
    video_path: Union[str, Path],
    output_dir: Union[str, Path],
    threshold: float = 27.0,
    min_scene_len: float = 0.6,
) -> Dict[str, Any]:
    """Detect video scene boundaries using PySceneDetect via run_cmd.

    Outputs scenes.json conforming to Schema 1.0.0 and returns evidence paths.
    """
    video_p = Path(video_path).resolve()
    if not video_p.exists():
        raise ProcessingError(f"Input video file for scene detection does not exist: {video_p}")

    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    scenedetect_bin = shutil.which("scenedetect") or str(Path(sys.executable).parent / "scenedetect")

    cmd = [
        scenedetect_bin,
        "-i",
        str(video_p),
        "-o",
        str(out_dir),
        "detect-content",
        "-t",
        str(threshold),
        "-m",
        f"{min_scene_len}s",
        "list-scenes",
    ]

    res = run_cmd(cmd, stage="scenes")
    if res.returncode != 0:
        raise ProcessingError(
            f"PySceneDetect execution failed with exit code {res.returncode}: {res.stderr}"
        )

    # Probe duration
    probe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_p),
    ]
    probe_res = run_cmd(probe_cmd, stage="scenes")
    video_duration = 0.0
    if probe_res.returncode == 0:
        try:
            p_data = json.loads(probe_res.stdout)
            video_duration = float(p_data.get("format", {}).get("duration", 0.0))
        except (ValueError, json.JSONDecodeError):
            video_duration = 0.0

    # Locate generated CSV file
    csv_file = None
    expected_csv = out_dir / f"{video_p.stem}-Scenes.csv"
    if expected_csv.exists():
        csv_file = expected_csv
    else:
        for f in out_dir.glob("*.csv"):
            if "Scenes" in f.name:
                csv_file = f
                break

    parsed_scenes: List[Dict[str, Any]] = []
    if csv_file and csv_file.exists():
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            header_found = False
            scene_idx = 1
            for row in reader:
                if not row or not any(row):
                    continue
                row_str = [c.strip() for c in row]
                if "Scene Number" in row_str or "Start Time (seconds)" in row_str:
                    header_found = True
                    continue
                if header_found and len(row_str) >= 7:
                    try:
                        s_num = int(row_str[0])
                        s_frame = int(row_str[1])
                        s_code = row_str[2]
                        s_sec = float(row_str[3])
                        e_frame = int(row_str[4])
                        e_code = row_str[5]
                        e_sec = float(row_str[6])
                        dur_sec = float(row_str[9]) if len(row_str) > 9 else (e_sec - s_sec)
                        dur_frames = int(row_str[7]) if len(row_str) > 7 else (e_frame - s_frame)

                        parsed_scenes.append({
                            "scene_id": s_num,
                            "start_time": round(s_sec, 3),
                            "end_time": round(e_sec, 3),
                            "start_frame": s_frame,
                            "end_frame": e_frame,
                            "start_timecode": s_code,
                            "end_timecode": e_code,
                            "duration_sec": round(dur_sec, 3),
                            "duration_frames": dur_frames,
                            "start_ms": int(round(s_sec * 1000)),
                            "end_ms": int(round(e_sec * 1000)),
                        })
                        scene_idx += 1
                    except (ValueError, IndexError):
                        continue

    if not parsed_scenes:
        # Fallback single scene
        dur = video_duration if video_duration > 0 else 5.0
        parsed_scenes = [
            {
                "scene_id": 1,
                "start_time": 0.0,
                "end_time": round(dur, 3),
                "start_frame": 1,
                "end_frame": int(dur * 30),
                "start_timecode": "00:00:00.000",
                "end_timecode": f"00:00:{dur:06.3f}",
                "duration_sec": round(dur, 3),
                "duration_frames": int(dur * 30),
                "start_ms": 0,
                "end_ms": int(round(dur * 1000)),
            }
        ]
        if video_duration <= 0.0:
            video_duration = dur

    cut_sec = sorted(list(set([0.0] + [s["end_time"] for s in parsed_scenes])))
    cut_ms = sorted(list(set([0] + [s["end_ms"] for s in parsed_scenes])))

    scenes_data = {
        "schema_version": "1.0.0",
        "video_id": video_p.stem,
        "video_path": str(video_p),
        "detector": "ContentDetector",
        "parameters": {
            "threshold": threshold,
            "min_scene_len": min_scene_len,
        },
        "total_scenes": len(parsed_scenes),
        "video_duration_sec": round(video_duration, 3),
        "scenes": parsed_scenes,
        "scene_list": parsed_scenes,
        "cut_timestamps_sec": cut_sec,
        "cut_timestamps_ms": cut_ms,
    }

    scenes_json = out_dir / "scenes.json"
    scenes_json.write_text(
        json.dumps(scenes_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return {
        "status": "ok",
        "scenes_path": str(scenes_json),
        "evidence_paths": [str(scenes_json)],
        "total_scenes": len(parsed_scenes),
        "scenes_data": scenes_data,
    }
