"""FFmpeg media processor module for youtube_clipper.

Provides FFmpegProcessor for clipping and re-encoding video files via FFmpeg subprocess.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Union

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
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                raise ProcessingError(
                    f"FFmpeg command execution failed with returncode {res.returncode}",
                    returncode=res.returncode,
                    stderr=res.stderr,
                    cmd=cmd,
                    exit_code=4,
                )
            if not outp.exists():
                raise ProcessingError(
                    f"FFmpeg execution completed with code 0 but output file was not created: {outp}",
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
