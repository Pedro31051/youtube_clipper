"""Custom exception hierarchy for youtube_clipper.

Provides a unified exception tree for validating inputs, downloading YouTube media,
processing clips with FFmpeg, and reporting clean CLI error messages.
"""

from typing import List, Optional


class ClipperError(Exception):
    """Base exception for all errors raised by youtube_clipper.

    Attributes:
        message (str): Human-readable error explanation.
        exit_code (int): Recommended CLI exit code (default: 1).
    """

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code

    def __str__(self) -> str:
        return self.message


class ValidationError(ClipperError):
    """Raised when input validation fails (e.g. invalid timestamps, range, or URL).

    Attributes:
        message (str): Explanation of validation failure.
        field (Optional[str]): Parameter or input field that failed validation.
        exit_code (int): Recommended CLI exit code (default: 2).
    """

    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        exit_code: int = 2,
    ) -> None:
        super().__init__(message, exit_code=exit_code)
        self.field = field


class DownloadError(ClipperError):
    """Raised when downloading stream media via yt-dlp fails.

    Attributes:
        message (str): Detailed error message.
        url (Optional[str]): Targeted YouTube URL.
        exit_code (int): Recommended CLI exit code (default: 3).
    """

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        exit_code: int = 3,
    ) -> None:
        super().__init__(message, exit_code=exit_code)
        self.url = url


class ProcessingError(ClipperError):
    """Raised when FFmpeg subprocess execution or media processing fails.

    Attributes:
        message (str): Error summary.
        returncode (Optional[int]): Process return exit code from FFmpeg.
        stderr (Optional[str]): Error output captured from FFmpeg stderr stream.
        cmd (Optional[List[str]]): Command-line argument list passed to FFmpeg.
        exit_code (int): Recommended CLI exit code (default: 4).
    """

    def __init__(
        self,
        message: str,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
        cmd: Optional[List[str]] = None,
        exit_code: int = 4,
    ) -> None:
        super().__init__(message, exit_code=exit_code)
        self.returncode = returncode
        self.stderr = stderr
        self.cmd = cmd


class FFmpegNotFoundError(ProcessingError):
    """Raised when the ffmpeg executable binary cannot be located on system PATH.

    Attributes:
        message (str): Error message detailing missing binary.
        exit_code (int): Recommended CLI exit code (default: 5).
    """

    def __init__(
        self,
        message: str = "FFmpeg executable not found. Please install ffmpeg and ensure it is in your system PATH.",
        exit_code: int = 5,
    ) -> None:
        super().__init__(
            message,
            returncode=None,
            stderr=None,
            cmd=None,
            exit_code=exit_code,
        )
