"""
Video Formatter Module for YouTube Clipper.
Provides FFmpeg filters to convert horizontal 16:9 videos into 9:16 vertical Shorts/Reels,
applying center crop or blurred background fill.
"""

import functools
import os
import shutil
from typing import Optional, Union

from cortes.log import run_cmd
from youtube_clipper.exceptions import ProcessingError


@functools.lru_cache(maxsize=1)
def detect_h264_encoder(ffmpeg_bin: str = "ffmpeg") -> str:
    """Detects if h264_nvenc is available and operational on the host system.

    Returns 'h264_nvenc' if hardware acceleration is supported, else 'libx264'.
    """
    if not shutil.which(ffmpeg_bin):
        return "libx264"
    try:
        res = run_cmd(
            [ffmpeg_bin, "-y", "-f", "lavfi", "-i", "nullsrc", "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"],
            stage="transform",
            audit=False,
        )
        if res.returncode == 0:
            return "h264_nvenc"
    except Exception:
        pass
    return "libx264"


class VideoFormatter:
    """FFmpeg video layout transform engine."""

    @staticmethod
    def build_vertical_filter(
        width: Union[int, str] = 1080,
        height: int = 1920,
        mode: str = "blur_background",
        sigma: float = 12.0,
    ) -> str:
        """
        Builds FFmpeg video filter for 9:16 vertical layout.
        Modes:
        - 'blur_background' / 'split_blur': Low-res gblur background with scaled video foreground.
        - 'crop_center': Crops center of 16:9 video to 9:16 aspect ratio (1080x1920).
        """
        if isinstance(width, str):
            mode = width
            width = 1080
            height = 1920

        if mode in ("blur_background", "split_blur"):
            low_w = int(width) // 4
            low_h = int(height) // 4
            return (
                f"split[bg][fg];"
                f"[bg]scale={low_w}:{low_h}:force_original_aspect_ratio=increase,crop={low_w}:{low_h},gblur=sigma={sigma},scale={width}:{height}[blurred];"
                f"[fg]scale={width}:-2[scaled_fg];"
                f"[blurred][scaled_fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2"
            )
        elif mode == "crop_center":
            return f"crop=ih*9/16:ih:(iw-ow)/2:0,scale={width}:{height}"
        else:
            raise ValueError(f"Unsupported vertical format mode: {mode}")

    @classmethod
    def convert_to_vertical(
        cls,
        input_path: str,
        output_path: str,
        mode: str = "blur_background",
        target_aspect: str = "9:16",
        start: Optional[float] = None,
        end: Optional[float] = None,
        encoder: Optional[str] = None,
        ffmpeg_bin: str = "ffmpeg",
        sigma: float = 12.0,
    ) -> str:
        """Converts input video into 9:16 vertical MP4 format in a single pass.

        Supports optional start and end timestamps for single-pass cutting + vertical conversion.
        Detects hardware NVENC encoder automatically if encoder is not explicitly specified.

        Returns output_path on success.
        Raises ProcessingError on FFmpeg subprocess failure or empty/missing output file.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        if start is not None and end is not None:
            if float(start) >= float(end):
                raise ProcessingError(
                    f"Invalid timestamp range: start ({start}) must be strictly less than end ({end}).",
                    returncode=1,
                    stderr="Invalid timestamp range",
                )

        filter_str = cls.build_vertical_filter(mode=mode, sigma=sigma)

        cmd = [ffmpeg_bin, "-y"]

        if start is not None:
            cmd.extend(["-ss", str(float(start))])

        cmd.extend(["-i", str(input_path)])

        if end is not None:
            if start is not None:
                duration = float(end) - float(start)
                cmd.extend(["-t", str(duration)])
            else:
                cmd.extend(["-to", str(float(end))])

        cmd.extend(["-vf", filter_str])

        selected_encoder = encoder or detect_h264_encoder(ffmpeg_bin)
        codec_arg_index = len(cmd)
        if selected_encoder == "h264_nvenc":
            cmd.extend(["-c:v", "h264_nvenc", "-preset", "p4"])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"])

        cmd.extend([
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            str(output_path)
        ])

        res = run_cmd(cmd, stage="transform")
        if (
            res.returncode != 0
            and selected_encoder == "h264_nvenc"
            and encoder is None
        ):
            if os.path.exists(output_path):
                os.unlink(output_path)
            fallback_cmd = list(cmd)
            fallback_cmd[codec_arg_index : codec_arg_index + 4] = [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
            ]
            res = run_cmd(fallback_cmd, stage="transform")

        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return str(output_path)
        else:
            stderr_msg = res.stderr if res.stderr is not None else ""
            raise ProcessingError(
                f"FFmpeg vertical conversion failed: {stderr_msg}",
                returncode=res.returncode,
                stderr=stderr_msg
            )
