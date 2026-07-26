"""Unit tests for timestamp and input validation engine and exception hierarchy."""

import pytest
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


class TestClipperExceptions:
    """Tests for custom exception classes."""

    def test_clipper_error_base(self):
        err = ClipperError("Base error message")
        assert str(err) == "Base error message"
        assert err.message == "Base error message"
        assert err.exit_code == 1

    def test_validation_error(self):
        err = ValidationError("Invalid input", field="start")
        assert isinstance(err, ClipperError)
        assert err.message == "Invalid input"
        assert err.field == "start"
        assert err.exit_code == 2

    def test_download_error(self):
        err = DownloadError("Stream fetch failed", url="https://youtube.com/watch?v=dQw4w9WgXcQ")
        assert isinstance(err, ClipperError)
        assert err.message == "Stream fetch failed"
        assert err.url == "https://youtube.com/watch?v=dQw4w9WgXcQ"
        assert err.exit_code == 3

    def test_processing_error(self):
        err = ProcessingError(
            "FFmpeg failed",
            returncode=1,
            stderr="Error opening input",
            cmd=["ffmpeg", "-i", "in.mp4"],
        )
        assert isinstance(err, ClipperError)
        assert err.message == "FFmpeg failed"
        assert err.returncode == 1
        assert err.stderr == "Error opening input"
        assert err.cmd == ["ffmpeg", "-i", "in.mp4"]
        assert err.exit_code == 4

    def test_ffmpeg_not_found_error(self):
        err = FFmpegNotFoundError()
        assert isinstance(err, ProcessingError)
        assert isinstance(err, ClipperError)
        assert "FFmpeg executable not found" in err.message
        assert err.exit_code == 5


class TestParseTimestamp:
    """Tests for parse_timestamp function."""

    @pytest.mark.parametrize(
        "input_val, expected",
        [
            ("45", 45.0),
            ("45.5", 45.5),
            ("0", 0.0),
            (0, 0.0),
            (120, 120.0),
            (12.5, 12.5),
            ("05:30", 330.0),
            ("05:30.5", 330.5),
            ("90:00", 5400.0),  # MM:SS with MM > 59
            ("01:02:03", 3723.0),
            ("01:02:03.456", 3723.456),
            ("00:00:00", 0.0),
            ("  01:30  ", 90.0),  # Whitespace handling
        ],
    )
    def test_parse_timestamp_valid_inputs(self, input_val, expected):
        assert parse_timestamp(input_val) == pytest.approx(expected)

    @pytest.mark.parametrize(
        "invalid_input",
        [
            "",
            "   ",
            "-10",
            "-01:30",
            "-5.5",
            "05:60",  # SS >= 60 in MM:SS
            "01:60:00",  # MM >= 60 in HH:MM:SS
            "01:05:60",  # SS >= 60 in HH:MM:SS
            "01:02:03:04",  # Too many colons
            "abc",
            "01:ab:00",
            None,
            [1, 2],  # Invalid type
        ],
    )
    def test_parse_timestamp_invalid_inputs(self, invalid_input):
        with pytest.raises(ValidationError):
            parse_timestamp(invalid_input)

    @pytest.mark.parametrize("bool_val", [True, False])
    def test_parse_timestamp_bool_inputs_raise_validation_error(self, bool_val):
        with pytest.raises(ValidationError, match="Boolean values are not valid timestamps"):
            parse_timestamp(bool_val)

    @pytest.mark.parametrize(
        "nan_inf_input",
        [
            float("nan"),
            float("inf"),
            float("-inf"),
            "nan",
            "NaN",
            "NAN",
            "inf",
            "Inf",
            "INFINITY",
            "-inf",
            "1e309",
            "-1e309",
            "00:00:nan",
            "00:00:inf",
        ],
    )
    def test_parse_timestamp_nan_inf_inputs_raise_validation_error(self, nan_inf_input):
        with pytest.raises(ValidationError):
            parse_timestamp(nan_inf_input)

    @pytest.mark.parametrize(
        "space_input",
        [
            "12:34: 56",
            "12: 34:56",
            "12 :34:56",
            "05: 30",
        ],
    )
    def test_parse_timestamp_colon_space_inputs_raise_validation_error(self, space_input):
        with pytest.raises(ValidationError):
            parse_timestamp(space_input)


class TestValidateTimeRange:
    """Tests for validate_time_range function."""

    def test_valid_start_and_end(self):
        start, end = validate_time_range("00:10", "00:40", None)
        assert start == 10.0
        assert end == 40.0

    def test_default_start_with_end(self):
        start, end = validate_time_range(None, "01:00", None)
        assert start == 0.0
        assert end == 60.0

    def test_empty_start_string_with_end(self):
        start, end = validate_time_range("", "01:00", None)
        assert start == 0.0
        assert end == 60.0

    def test_start_with_duration(self):
        start, end = validate_time_range("00:30", None, "15")
        assert start == 30.0
        assert end == 45.0

    def test_default_start_with_duration(self):
        start, end = validate_time_range(None, None, "30.5")
        assert start == 0.0
        assert end == 30.5

    def test_numeric_inputs(self):
        start, end = validate_time_range(10, 50, None)
        assert start == 10.0
        assert end == 50.0

    def test_conflict_end_and_duration_raises_error(self):
        with pytest.raises(ValidationError, match="Cannot specify both"):
            validate_time_range("10", "30", "20")

    def test_start_equal_to_end_raises_error(self):
        with pytest.raises(ValidationError, match="strictly less than"):
            validate_time_range("30", "30", None)

    def test_start_greater_than_end_raises_error(self):
        with pytest.raises(ValidationError, match="strictly less than"):
            validate_time_range("40", "20", None)

    def test_zero_duration_raises_error(self):
        with pytest.raises(ValidationError, match="greater than zero"):
            validate_time_range("10", None, "0")

    def test_negative_duration_raises_error(self):
        with pytest.raises(ValidationError):
            validate_time_range("10", None, "-5")

    def test_negative_start_raises_error(self):
        with pytest.raises(ValidationError):
            validate_time_range("-10", "30", None)

    def test_neither_end_nor_duration_raises_error(self):
        with pytest.raises(ValidationError, match="Either end time"):
            validate_time_range(None, None, None)

    @pytest.mark.parametrize("bool_val", [True, False])
    def test_validate_time_range_bool_inputs_raise_validation_error(self, bool_val):
        with pytest.raises(ValidationError, match="Boolean values are not valid timestamps"):
            validate_time_range(bool_val, 10, None)
        with pytest.raises(ValidationError, match="Boolean values are not valid timestamps"):
            validate_time_range(0, bool_val, None)
        with pytest.raises(ValidationError, match="Boolean values are not valid timestamps"):
            validate_time_range(0, None, bool_val)

    @pytest.mark.parametrize(
        "invalid_val",
        [
            "nan",
            "inf",
            float("nan"),
            float("inf"),
            "1e309",
            "00:00:nan",
        ],
    )
    def test_validate_time_range_nan_inf_inputs_raise_validation_error(self, invalid_val):
        with pytest.raises(ValidationError):
            validate_time_range(invalid_val, "10", None)
        with pytest.raises(ValidationError):
            validate_time_range("0", invalid_val, None)
        with pytest.raises(ValidationError):
            validate_time_range("0", None, invalid_val)


class TestIsYoutubeUrl:
    """Tests for is_youtube_url function."""

    @pytest.mark.parametrize(
        "url",
        [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "www.youtube.com/watch?v=dQw4w9WgXcQ",
            "youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://gaming.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://tv.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/dQw4w9WgXcQ",
            "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "https://www.youtube.com/live/dQw4w9WgXcQ",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=100s&feature=shared",
        ],
    )
    def test_valid_youtube_urls(self, url):
        assert is_youtube_url(url) is True

    @pytest.mark.parametrize(
        "invalid_url",
        [
            "https://vimeo.com/12345678",
            "https://google.com",
            "https://www.youtube.com/",
            "https://www.youtube.com/watch?v=",
            "https://www.youtube.com/watch?notv=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?my_v=dQw4w9WgXcQ",
            "https://www.youtube.com/watch?prev=dQw4w9WgXcQ",
            "https://youtu.be/short",
            "/tmp/video.mp4",
            "",
            None,
            12345,
        ],
    )
    def test_invalid_youtube_urls(self, invalid_url):
        assert is_youtube_url(invalid_url) is False


class TestValidateInputSource:
    """Tests for validate_input_source function."""

    def test_valid_youtube_url_returns_url(self):
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_input_source(url) == url

    def test_valid_youtube_subdomains_return_url(self):
        music_url = "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
        gaming_url = "https://gaming.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validate_input_source(music_url) == music_url
        assert validate_input_source(gaming_url) == gaming_url

    def test_fake_v_parameter_url_raises_error(self):
        fake_url = "https://www.youtube.com/watch?notv=dQw4w9WgXcQ"
        with pytest.raises(ValidationError, match="Invalid input source"):
            validate_input_source(fake_url)

    def test_valid_youtube_url_with_whitespace_returns_trimmed(self):
        url = "   https://www.youtube.com/watch?v=dQw4w9WgXcQ   "
        assert validate_input_source(url) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_existing_local_file_returns_path(self, tmp_path):
        dummy_file = tmp_path / "test.mp4"
        dummy_file.write_text("fake video content")
        assert validate_input_source(str(dummy_file)) == str(dummy_file)

    def test_nonexistent_local_file_raises_error(self):
        with pytest.raises(ValidationError, match="Invalid input source"):
            validate_input_source("/path/to/nonexistent_video.mp4")

    def test_directory_path_raises_error(self, tmp_path):
        with pytest.raises(ValidationError, match="directory"):
            validate_input_source(str(tmp_path))

    def test_empty_string_raises_error(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_input_source("")

    def test_none_input_raises_error(self):
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_input_source(None)  # type: ignore[arg-type]
