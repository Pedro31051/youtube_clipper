"""
Video Formatter Module for YouTube Clipper.
Provides FFmpeg filters to convert horizontal 16:9 videos into 9:16 vertical Shorts/Reels,
applying center crop or blurred background fill.
"""

import functools
import math
import os
import re
import shutil
import tempfile
from typing import Optional, Union

from cortes.log import audited, run_cmd
from youtube_clipper.exceptions import ProcessingError


@functools.lru_cache(maxsize=1)
def detect_h264_encoder(ffmpeg_bin: str = "ffmpeg") -> str:
    """Return NVENC when FFmpeg advertises it and a local NVIDIA device exists.

    The real render remains the operational proof and already retries with libx264
    on failure. Avoiding a throwaway NVENC encode removes GPU initialization from
    the latency of every fresh process.
    """
    if not shutil.which(ffmpeg_bin):
        return "libx264"
    if os.name == "posix" and not (
        os.path.exists("/dev/nvidia0") and os.path.exists("/dev/nvidiactl")
    ):
        return "libx264"
    try:
        result = run_cmd(
            [ffmpeg_bin, "-hide_banner", "-encoders"],
            stage="transform",
            audit=False,
        )
        if result.returncode == 0 and "h264_nvenc" in str(result.stdout or ""):
            return "h264_nvenc"
    except Exception:
        pass
    return "libx264"
    """FFmpeg video layout transform engine."""


class VideoFormatter:

    @staticmethod
    def build_vertical_filter(
        width: Union[int, str] = 1080,
        height: int = 1920,
        mode: str = "blur_background",
        sigma: float = 12.0,
        crop_focus: str = "center",
        overlay_text: Optional[str] = None,
        overlay_textfile: Optional[str] = None,
        overlay_position: str = "top",
    ) -> str:
        """Build the FFmpeg filter graph for the requested vertical layout.

        ``crop_focus`` selects the horizontal crop anchor. When ``overlay_text``
        is provided, a readable editorial title is burned into the video.
        """
        if isinstance(width, str):
            mode = width
            width = 1080
            height = 1920

        if not math.isfinite(float(sigma)) or not 0.0 <= float(sigma) <= 50.0:
            raise ValueError("Blur sigma must be a finite number between 0 and 50")
        if crop_focus not in {"left", "center", "right"}:
            raise ValueError("Crop focus must be one of: left, center, right")
        if overlay_position not in {"top", "bottom"}:
            raise ValueError("Overlay position must be one of: top, bottom")

        if mode in ("blur_background", "split_blur"):
            low_w = int(width) // 4
            low_h = int(height) // 4
            filter_str = (
                f"split[bg][fg];"
                f"[bg]scale={low_w}:{low_h}:force_original_aspect_ratio=increase,crop={low_w}:{low_h},gblur=sigma={sigma},scale={width}:{height}[blurred];"
                f"[fg]scale={width}:-2[scaled_fg];"
                f"[blurred][scaled_fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2"
            )
        elif mode == "crop_center":
            crop_x = {
                "left": "0",
                "center": "(iw-ow)/2",
                "right": "iw-ow",
            }[crop_focus]
            filter_str = f"crop=ih*9/16:ih:{crop_x}:0,scale={width}:{height}"
        else:
            raise ValueError(f"Unsupported vertical format mode: {mode}")

        if overlay_text or overlay_textfile:
            if overlay_textfile:
                escaped_path = (
                    str(overlay_textfile).replace("\\", r"\\")
                    .replace("'", r"\'")
                    .replace(":", r"\:")
                )
                text_source = f"textfile='{escaped_path}'"
            else:
                cleaned_text = re.sub(r"[\x00-\x1f\x7f]+", " ", str(overlay_text)).strip()
                escaped_text = (
                    cleaned_text.replace("\\", r"\\")
                    .replace("'", r"\'")
                    .replace(":", r"\:")
                    .replace("%", r"\%")
                    .replace(",", r"\,")
                    .replace(";", r"\;")
                    .replace("[", r"\[")
                    .replace("]", r"\]")
                )
                if not escaped_text:
                    raise ValueError("Overlay text cannot be empty")
                text_source = f"text='{escaped_text}'"
            box_y = "80" if overlay_position == "top" else "ih-300"
            text_y = "150" if overlay_position == "top" else "h-text_h-150"
            filter_str += (
                f",drawbox=x=60:y={box_y}:w=iw-120:h=220:"
                "color=black@0.62:t=fill,"
                f"drawtext={text_source}:fontcolor=white:fontsize=58:"
                f"x=(w-text_w)/2:y={text_y}:fix_bounds=true"
            )

        return filter_str

    @classmethod
    @audited(
        stage="transform",
        action="media.convert_vertical",
        component="youtube_clipper.video_formatter",
    )
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
        crop_focus: str = "center",
        include_audio: bool = True,
        overlay_text: Optional[str] = None,
        overlay_position: str = "top",
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

        if not isinstance(include_audio, bool):
            raise ValueError("include_audio must be a boolean")

        overlay_file_path: Optional[str] = None
        if overlay_text is not None:
            cleaned_overlay = re.sub(r"[\x00-\x1f\x7f]+", " ", str(overlay_text)).strip()
            if not cleaned_overlay:
                raise ValueError("Overlay text cannot be empty")
            output_parent = os.path.dirname(os.path.abspath(output_path))
            os.makedirs(output_parent, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".overlay_",
                suffix=".txt",
                dir=output_parent,
                delete=False,
            ) as overlay_file:
                overlay_file.write(cleaned_overlay)
                overlay_file_path = overlay_file.name

        try:
            filter_str = cls.build_vertical_filter(
                mode=mode,
                sigma=sigma,
                crop_focus=crop_focus,
                overlay_textfile=overlay_file_path,
                overlay_position=overlay_position,
            )
        except Exception:
            if overlay_file_path and os.path.exists(overlay_file_path):
                os.unlink(overlay_file_path)
            raise

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

        cmd.extend(["-pix_fmt", "yuv420p"])
        if include_audio:
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        else:
            cmd.append("-an")
        cmd.append(str(output_path))

        try:
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
        finally:
            if overlay_file_path and os.path.exists(overlay_file_path):
                os.unlink(overlay_file_path)

        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return str(output_path)
        else:
            stderr_msg = res.stderr if res.stderr is not None else ""
            raise ProcessingError(
                f"FFmpeg vertical conversion failed: {stderr_msg}",
                returncode=res.returncode,
                stderr=stderr_msg
            )
