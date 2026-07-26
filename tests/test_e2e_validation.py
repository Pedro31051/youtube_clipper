"""End-to-end and unit test suite for Custom Exceptions Engine and Input & Timestamp Validation Engine.

Covers Feature 2 (Custom Exceptions Engine) and Feature 3 (Input & Timestamp Validation Engine)
across Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner Cases).
"""

from pathlib import Path
import pytest

try:
    from youtube_clipper.exceptions import (
        ClipperError,
        DownloadError,
        FFmpegNotFoundError,
        ProcessingError,
        ValidationError,
    )
    from youtube_clipper.validator import (
        is_youtube_url,
        parse_timestamp,
        validate_input_source,
        validate_time_range,
    )
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from youtube_clipper.exceptions import (
        ClipperError,
        DownloadError,
        FFmpegNotFoundError,
        ProcessingError,
        ValidationError,
    )
    from youtube_clipper.validator import (
        is_youtube_url,
        parse_timestamp,
        validate_input_source,
        validate_time_range,
    )


# ============================================================================
# Feature 2: Custom Exceptions Engine Tests
# ============================================================================

class TestCustomExceptionsEngine:
    """Tier 1 & Tier 2 test suite for Feature 2: Custom Exception Hierarchy."""

    def test_clipper_error_base_properties(self):
        """Tier 1: Base ClipperError instantiates correctly with default and custom exit codes."""
        err_default = ClipperError("Base system failure")
        assert str(err_default) == "Base system failure"
        assert err_default.message == "Base system failure"
        assert err_default.exit_code == 1

        err_custom = ClipperError("Custom exit code error", exit_code=99)
        assert err_custom.message == "Custom exit code error"
        assert err_custom.exit_code == 99

    def test_validation_error_properties(self):
        """Tier 1: ValidationError supports field attribute and defaults to exit code 2."""
        err = ValidationError("Invalid timestamp format", field="start_time")
        assert isinstance(err, ClipperError)
        assert str(err) == "Invalid timestamp format"
        assert err.message == "Invalid timestamp format"
        assert err.field == "start_time"
        assert err.exit_code == 2

    def test_download_error_properties(self):
        """Tier 1: DownloadError supports url attribute and defaults to exit code 3."""
        target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        err = DownloadError("Failed to fetch stream metadata", url=target_url)
        assert isinstance(err, ClipperError)
        assert str(err) == "Failed to fetch stream metadata"
        assert err.message == "Failed to fetch stream metadata"
        assert err.url == target_url
        assert err.exit_code == 3

    def test_processing_error_properties(self):
        """Tier 1: ProcessingError captures returncode, stderr, cmd, and defaults to exit code 4."""
        cmd = ["ffmpeg", "-ss", "0", "-i", "in.mp4", "out.mp4"]
        err = ProcessingError(
            "FFmpeg process terminated unexpectedly",
            returncode=127,
            stderr="Decoder error",
            cmd=cmd,
        )
        assert isinstance(err, ClipperError)
        assert str(err) == "FFmpeg process terminated unexpectedly"
        assert err.message == "FFmpeg process terminated unexpectedly"
        assert err.returncode == 127
        assert err.stderr == "Decoder error"
        assert err.cmd == cmd
        assert err.exit_code == 4

    def test_ffmpeg_not_found_error_properties(self):
        """Tier 1: FFmpegNotFoundError defaults to standard error message and exit code 5."""
        err = FFmpegNotFoundError()
        assert isinstance(err, ProcessingError)
        assert isinstance(err, ClipperError)
        assert "FFmpeg executable not found" in str(err)
        assert err.message == "FFmpeg executable not found. Please install ffmpeg and ensure it is in your system PATH."
        assert err.returncode is None
        assert err.stderr is None
        assert err.cmd is None
        assert err.exit_code == 5

    def test_exceptions_inheritance_hierarchy(self):
        """Tier 2: Verify exact class inheritance relationships across the exception tree."""
        assert issubclass(ValidationError, ClipperError)
        assert issubclass(DownloadError, ClipperError)
        assert issubclass(ProcessingError, ClipperError)
        assert issubclass(FFmpegNotFoundError, ProcessingError)
        assert issubclass(FFmpegNotFoundError, ClipperError)
        assert issubclass(ClipperError, Exception)

    def test_exceptions_polymorphic_catching(self):
        """Tier 2: Verify base exception ClipperError catches all subclass exception instances."""
        exceptions_to_test = [
            ValidationError("Val err"),
            DownloadError("Dl err"),
            ProcessingError("Proc err"),
            FFmpegNotFoundError(),
        ]
        for exc in exceptions_to_test:
            with pytest.raises(ClipperError) as exc_info:
                raise exc
            assert exc_info.value is exc

        # Also verify ProcessingError catches FFmpegNotFoundError
        with pytest.raises(ProcessingError) as exc_info:
            raise FFmpegNotFoundError()
        assert isinstance(exc_info.value, FFmpegNotFoundError)

    def test_exceptions_optional_attributes_defaults(self):
        """Tier 2: Verify optional attributes default to None when omitted."""
        val_err = ValidationError("Simple message")
        assert val_err.field is None

        dl_err = DownloadError("Network error")
        assert dl_err.url is None

        proc_err = ProcessingError("Process killed")
        assert proc_err.returncode is None
        assert proc_err.stderr is None
        assert proc_err.cmd is None


# ============================================================================
# Feature 3: Timestamp Parsing Tests
# ============================================================================

class TestParseTimestampEngine:
    """Tier 1 & Tier 2 test suite for parse_timestamp function."""

    @pytest.mark.parametrize(
        "input_str, expected_seconds",
        [
            ("01:02:03", 3723.0),
            ("02:30:15", 9015.0),
            ("00:00:00", 0.0),
            ("05:30", 330.0),
            ("12:45", 765.0),
            ("00:00", 0.0),
            ("90:00", 5400.0),
            ("45", 45.0),
            ("0", 0.0),
            ("120", 120.0),
            ("45.5", 45.5),
            ("0.25", 0.25),
            ("01:02:03.456", 3723.456),
        ],
    )
    def test_parse_timestamp_tier1_valid_formats(self, input_str, expected_seconds):
        """Tier 1: Standard valid timestamp formats (HH:MM:SS, MM:SS, SS, SS.s, 00:00:00)."""
        res = parse_timestamp(input_str)
        assert res == pytest.approx(expected_seconds)

    @pytest.mark.parametrize(
        "numeric_val, expected_seconds",
        [
            (0, 0.0),
            (120, 120.0),
            (45.5, 45.5),
            (0.0, 0.0),
        ],
    )
    def test_parse_timestamp_tier1_numeric_types(self, numeric_val, expected_seconds):
        """Tier 1: Direct int and float numeric inputs."""
        assert parse_timestamp(numeric_val) == pytest.approx(expected_seconds)

    @pytest.mark.parametrize(
        "invalid_format",
        [
            "abc",
            "12:34:56:78",
            "01:ab:00",
            "12:34:56.78:90",
            "1:2:3:4",
        ],
    )
    def test_parse_timestamp_tier2_invalid_string_formats(self, invalid_format):
        """Tier 2: Malformed timestamp format strings raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            parse_timestamp(invalid_format)
        assert exc_info.value.field == "timestamp"

    @pytest.mark.parametrize(
        "negative_input",
        [
            "-05:00",
            "-10",
            "-01:30",
            "-5.5",
            -10,
            -0.5,
        ],
    )
    def test_parse_timestamp_tier2_negative_timestamps(self, negative_input):
        """Tier 2: Negative timestamps (string or numeric) raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            parse_timestamp(negative_input)
        assert "negative" in str(exc_info.value).lower()

    @pytest.mark.parametrize(
        "overflow_input",
        [
            "01:60:00",  # MM >= 60 in HH:MM:SS
            "05:60",     # SS >= 60 in MM:SS
            "01:05:60",  # SS >= 60 in HH:MM:SS
            "00:60:30",  # MM >= 60 in HH:MM:SS
        ],
    )
    def test_parse_timestamp_tier2_overflow_components(self, overflow_input):
        """Tier 2: Overflow minutes/seconds (>= 60) raise ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            parse_timestamp(overflow_input)
        assert "must be less than 60" in str(exc_info.value)

    @pytest.mark.parametrize(
        "empty_or_invalid_type",
        [
            "",
            "   ",
            None,
            [123],
            {"time": 10},
        ],
    )
    def test_parse_timestamp_tier2_empty_and_invalid_types(self, empty_or_invalid_type):
        """Tier 2: Empty strings, None, and invalid types raise ValidationError."""
        with pytest.raises(ValidationError):
            parse_timestamp(empty_or_invalid_type)  # type: ignore[arg-type]


# ============================================================================
# Feature 3: Time Range Validation Tests
# ============================================================================

class TestValidateTimeRangeEngine:
    """Tier 1 & Tier 2 test suite for validate_time_range function."""

    def test_validate_time_range_tier1_valid_start_and_end(self):
        """Tier 1: Valid start and end timestamp strings."""
        start, end = validate_time_range("00:10", "00:40", None)
        assert start == 10.0
        assert end == 40.0

    def test_validate_time_range_tier1_start_only(self):
        """Tier 1: Valid start string with end string specified."""
        start, end = validate_time_range("00:30", "01:00", None)
        assert start == 30.0
        assert end == 60.0

    def test_validate_time_range_tier1_end_only_default_start(self):
        """Tier 1: End timestamp specified, start omitted/empty (defaults start to 0.0)."""
        start, end = validate_time_range(None, "01:00", None)
        assert start == 0.0
        assert end == 60.0

        start_empty, end_empty = validate_time_range("", "01:00", None)
        assert start_empty == 0.0
        assert end_empty == 60.0

    def test_validate_time_range_tier1_start_and_duration(self):
        """Tier 1: Start timestamp with duration specified."""
        start, end = validate_time_range("00:30", None, "15")
        assert start == 30.0
        assert end == 45.0

        start_def, end_def = validate_time_range(None, None, "30.5")
        assert start_def == 0.0
        assert end_def == 30.5

    def test_validate_time_range_tier2_start_ge_end(self):
        """Tier 2: start >= end condition raises ValidationError."""
        # start == end
        with pytest.raises(ValidationError, match="strictly less than"):
            validate_time_range("30", "30", None)

        # start > end
        with pytest.raises(ValidationError, match="strictly less than"):
            validate_time_range("01:00", "00:30", None)

    def test_validate_time_range_tier2_negative_start(self):
        """Tier 2: Negative start timestamp raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_time_range("-10", "30", None)

    def test_validate_time_range_tier2_zero_end(self):
        """Tier 2: End timestamp equal to zero or <= start raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_time_range("0", "0", None)

        with pytest.raises(ValidationError):
            validate_time_range("10", "0", None)

    def test_validate_time_range_tier2_conflicting_end_and_duration(self):
        """Tier 2: Providing both --end and --duration simultaneously raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_time_range("10", "30", "20")
        assert "Cannot specify both end time and duration" in str(exc_info.value)
        assert exc_info.value.field == "time_range"

    def test_validate_time_range_tier2_negative_or_zero_duration(self):
        """Tier 2: Zero or negative clip duration raises ValidationError."""
        with pytest.raises(ValidationError, match="greater than zero"):
            validate_time_range("10", None, "0")

        with pytest.raises(ValidationError):
            validate_time_range("10", None, "-5")

    def test_validate_time_range_tier2_neither_end_nor_duration(self):
        """Tier 2: Omitting both end and duration raises ValidationError."""
        with pytest.raises(ValidationError, match="Either end time"):
            validate_time_range(None, None, None)

        with pytest.raises(ValidationError):
            validate_time_range("10", "", "")

    def test_validate_time_range_tier2_invalid_duration_format(self):
        """Tier 2: Invalid duration format raises ValidationError."""
        with pytest.raises(ValidationError):
            validate_time_range("10", None, "invalid_duration")


# ============================================================================
# Feature 3: YouTube URL Detection Tests
# ============================================================================

class TestIsYoutubeUrlEngine:
    """Tier 1 & Tier 2 test suite for is_youtube_url function."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "www.youtube.com/watch?v=dQw4w9WgXcQ",
            "youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        ],
    )
    def test_is_youtube_url_tier1_valid_urls(self, url):
        """Tier 1: Standard YouTube URLs (watch, shorts, embed, live, mobile, short-url)."""
        assert is_youtube_url(url) is True

    def test_is_youtube_url_tier1_music_youtube_url(self):
        """Tier 1: music.youtube.com URL format (documented as Tier 1 requirement)."""
        assert is_youtube_url("https://music.youtube.com/watch?v=dQw4w9WgXcQ") is True

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "http://",
            "https://vimeo.com/12345678",
            "https://google.com",
            "https://dailymotion.com/video/x7gnn3",
            "ftp://youtube.com/watch?v=dQw4w9WgXcQ",
        ],
    )
    def test_is_youtube_url_tier2_invalid_domains_and_missing_host(self, invalid_url):
        """Tier 2: Non-YouTube domains, missing host, and unsupported protocols."""
        assert is_youtube_url(invalid_url) is False

    @pytest.mark.parametrize(
        "malformed_url",
        [
            "https://www.youtube.com/",
            "https://www.youtube.com/watch?v=",
            "https://youtu.be/short",
            "https://www.youtube.com/watch?v=123",
            "/tmp/video.mp4",
        ],
    )
    def test_is_youtube_url_tier2_malformed_urls(self, malformed_url):
        """Tier 2: Malformed YouTube URLs (missing or invalid 11-char video ID)."""
        assert is_youtube_url(malformed_url) is False

    @pytest.mark.parametrize(
        "non_string_input",
        [
            "",
            "   ",
            None,
            12345,
            ["https://youtube.com/watch?v=dQw4w9WgXcQ"],
        ],
    )
    def test_is_youtube_url_tier2_non_string_and_empty_inputs(self, non_string_input):
        """Tier 2: Empty strings, None, integers, and non-string types return False safely."""
        assert is_youtube_url(non_string_input) is False  # type: ignore[arg-type]


# ============================================================================
# Feature 3: Input Source Validation Tests
# ============================================================================

class TestValidateInputSourceEngine:
    """Tier 1 & Tier 2 test suite for validate_input_source function."""

    def test_validate_input_source_tier1_youtube_url(self):
        """Tier 1: Valid YouTube URL returns normalized input string."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_input_source(url) == url

        url_padded = "   https://youtu.be/dQw4w9WgXcQ   "
        assert validate_input_source(url_padded) == "https://youtu.be/dQw4w9WgXcQ"

    def test_validate_input_source_tier1_existing_local_file(self, tmp_path):
        """Tier 1: Existing local video file path returns normalized path string."""
        sample_file = tmp_path / "sample_input.mp4"
        sample_file.write_text("dummy binary video content")
        assert validate_input_source(str(sample_file)) == str(sample_file)

    def test_validate_input_source_tier2_nonexistent_local_file(self):
        """Tier 2: Non-existent local file path raises ValidationError."""
        nonexistent_path = "/nonexistent/path/to/missing_video.mp4"
        with pytest.raises(ValidationError) as exc_info:
            validate_input_source(nonexistent_path)
        assert "Invalid input source" in str(exc_info.value)
        assert exc_info.value.field == "input"

    @pytest.mark.parametrize("empty_val", ["", "   ", None])
    def test_validate_input_source_tier2_empty_and_none_inputs(self, empty_val):
        """Tier 2: Empty string or None input raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_input_source(empty_val)  # type: ignore[arg-type]
        assert "cannot be empty" in str(exc_info.value)
        assert exc_info.value.field == "input"

    def test_validate_input_source_tier2_directory_path(self, tmp_path):
        """Tier 2: Directory path (instead of file) raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_input_source(str(tmp_path))
        assert "is a directory" in str(exc_info.value)
        assert exc_info.value.field == "input"
