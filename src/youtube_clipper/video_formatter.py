"""
Video Formatter Module for YouTube Clipper.
Provides FFmpeg filters to convert horizontal 16:9 videos into 9:16 vertical Shorts/Reels,
applying center crop or blurred background fill.
"""

import os
from typing import Optional, Union

from cortes.log import run_cmd
from youtube_clipper.exceptions import ProcessingError


class VideoFormatter:
    """FFmpeg video layout transform engine."""

    @staticmethod
    def build_vertical_filter(
        width: Union[int, str] = 1080,
        height: int = 1920,
        mode: str = "blur_background"
    ) -> str:
        """
        Builds FFmpeg video filter for 9:16 vertical layout.
        Modes:
        - 'blur_background' / 'split_blur': Heavy blur background with scaled video foreground.
        - 'crop_center': Crops center of 16:9 video to 9:16 aspect ratio (1080x1920).
        """
        if isinstance(width, str):
            mode = width
            width = 1080
            height = 1920

        if mode in ("blur_background", "split_blur"):
            return (
                f"split[bg][fg];"
                f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=20:10[blurred];"
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
        ffmpeg_bin: str = "ffmpeg"
    ) -> str:
        """Converts input video into 9:16 vertical MP4 format.

        Returns output_path on success.
        Raises ProcessingError on FFmpeg subprocess failure or empty/missing output file.
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input file not found: {input_path}")

        filter_str = cls.build_vertical_filter(mode=mode)

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", input_path,
            "-vf", filter_str,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            output_path
        ]

        res = run_cmd(cmd, stage="transform")

        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return str(output_path)
        else:
            stderr_msg = res.stderr if res.stderr is not None else ""
            raise ProcessingError(
                f"FFmpeg vertical conversion failed: {stderr_msg}",
                returncode=res.returncode,
                stderr=stderr_msg
            )
