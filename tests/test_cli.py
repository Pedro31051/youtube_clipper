"""tests/test_cli.py - Unit test suite for youtube_clipper CLI parser module.

Covers ClipperArgumentParser, create_parser(), parse_args(), validate_cli_args(),
main() / cli_main() entrypoints, and function aliases.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

import pytest

from youtube_clipper.cli import (
    ClipperArgumentParser,
    build_parser,
    cli_main,
    create_parser,
    get_parser,
    main,
    parse_args,
    validate_cli_args,
)
from youtube_clipper.exceptions import ValidationError


class TestCreateParser:
    """Unit tests for create_parser() and function aliases."""

    def test_create_parser_returns_clipper_argument_parser(self) -> None:
        """Verify create_parser returns a ClipperArgumentParser instance."""
        parser = create_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert isinstance(parser, ClipperArgumentParser)
        assert parser.prog == "youtube_clipper"

    def test_parser_function_aliases(self) -> None:
        """Verify get_parser and build_parser return valid parser instances."""
        p1 = get_parser()
        p2 = build_parser()
        assert isinstance(p1, ClipperArgumentParser)
        assert isinstance(p2, ClipperArgumentParser)

    def test_parser_options_and_destinations(self) -> None:
        """Verify all required flags, options, and aliases exist in parser actions."""
        parser = create_parser()
        actions = {action.dest: action for action in parser._actions}

        assert "input" in actions
        assert "start" in actions
        assert "end" in actions
        assert "duration" in actions
        assert "output" in actions
        assert "fast" in actions
        assert "verbose" in actions

        assert "-s" in actions["start"].option_strings
        assert "--start" in actions["start"].option_strings

        assert "-e" in actions["end"].option_strings
        assert "--end" in actions["end"].option_strings

        assert "-d" in actions["duration"].option_strings
        assert "--duration" in actions["duration"].option_strings
        assert "--length" in actions["duration"].option_strings

        assert "-o" in actions["output"].option_strings
        assert "--output" in actions["output"].option_strings

        assert "--fast" in actions["fast"].option_strings
        assert "--copy" in actions["fast"].option_strings

        assert "-v" in actions["verbose"].option_strings
        assert "--verbose" in actions["verbose"].option_strings


class TestParseArgs:
    """Unit tests for parse_args()."""

    def test_parse_positional_input_url(self) -> None:
        """Verify parsing positional YouTube video URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        args = parse_args([url])
        assert args.input == url

    def test_parse_positional_input_file(self, dummy_video_file: Path) -> None:
        """Verify parsing positional local media file path."""
        args = parse_args([str(dummy_video_file)])
        assert args.input == str(dummy_video_file)

    def test_parse_default_values(self) -> None:
        """Verify default argument values when optional flags are omitted."""
        args = parse_args(["sample.mp4"])
        assert args.input == "sample.mp4"
        assert args.start is None
        assert args.end is None
        assert args.duration is None
        assert args.output is None
        assert args.fast is False
        assert args.verbose is False

    def test_parse_flag_aliases_duration_length(self) -> None:
        """Verify --duration, --length, and -d flags parse into duration destination."""
        args1 = parse_args(["sample.mp4", "--duration", "10"])
        args2 = parse_args(["sample.mp4", "--length", "10"])
        args3 = parse_args(["sample.mp4", "-d", "10"])
        assert args1.duration == args2.duration == args3.duration == "10"

    def test_parse_flag_aliases_fast_copy(self) -> None:
        """Verify --fast and --copy flags parse into fast destination."""
        args1 = parse_args(["sample.mp4", "--fast"])
        args2 = parse_args(["sample.mp4", "--copy"])
        assert args1.fast is True
        assert args2.fast is True

    def test_parse_flag_aliases_verbose(self) -> None:
        """Verify --verbose and -v flags parse into verbose destination."""
        args1 = parse_args(["sample.mp4", "--verbose"])
        args2 = parse_args(["sample.mp4", "-v"])
        assert args1.verbose is True
        assert args2.verbose is True

    def test_missing_input_raises_system_exit(self) -> None:
        """Verify omitting required input argument raises SystemExit with code 2."""
        with pytest.raises(SystemExit) as exc_info:
            parse_args([])
        assert exc_info.value.code == 2

    def test_conflicting_end_and_duration_raises_error(self) -> None:
        """Verify providing both --end and --duration raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            parse_args(["sample.mp4", "--end", "30", "--duration", "10"])
        assert "Cannot specify both" in exc_info.value.message


class TestValidateCLIArgs:
    """Unit tests for validate_cli_args()."""

    def test_validate_cli_args_valid_youtube_url(self) -> None:
        """Verify validate_cli_args with valid YouTube URL and timestamps."""
        parsed = parse_args(
            ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "-s", "00:01:00", "-e", "00:02:00", "-o", "out.mp4", "--fast"]
        )
        validated = validate_cli_args(parsed)
        assert validated["input"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert validated["start"] == 60.0
        assert validated["end"] == 120.0
        assert validated["output"] == "out.mp4"
        assert validated["fast"] is True

    def test_validate_cli_args_valid_local_file(self, dummy_video_file: Path) -> None:
        """Verify validate_cli_args with local file and duration."""
        parsed = parse_args([str(dummy_video_file), "-s", "0", "-d", "1.5"])
        validated = validate_cli_args(parsed)
        assert validated["input"] == str(dummy_video_file)
        assert validated["start"] == 0.0
        assert validated["end"] == 1.5

    def test_validate_cli_args_nonexistent_file_raises_validation_error(self) -> None:
        """Verify nonexistent local file path raises ValidationError."""
        parsed = parse_args(["nonexistent_video_file_xyz.mp4", "-s", "0", "-e", "10"])
        with pytest.raises(ValidationError) as exc_info:
            validate_cli_args(parsed)
        assert "Invalid input source" in exc_info.value.message

    def test_validate_cli_args_invalid_time_range_raises_validation_error(self, dummy_video_file: Path) -> None:
        """Verify start time greater than end time raises ValidationError."""
        parsed = parse_args([str(dummy_video_file), "-s", "30", "-e", "10"])
        with pytest.raises(ValidationError) as exc_info:
            validate_cli_args(parsed)
        assert "must be strictly less than end time" in exc_info.value.message


class TestCLIMain:
    """Unit tests for main() and cli_main() entrypoints."""

    def test_main_help_flag(self, cli_runner: Callable[..., Any]) -> None:
        """Verify main() handles --help flag correctly."""
        res = cli_runner(["--help"], target_func=main)
        assert res.exit_code == 0
        assert "usage: youtube_clipper" in res.stdout.lower()

    def test_main_valid_youtube_url_returns_zero(
        self, cli_runner: Callable[..., Any], mock_yt_dlp: Any, mock_ffmpeg: Any, tmp_path: Path
    ) -> None:
        """Verify main() returns exit code 0 for valid arguments."""
        out_file = str(tmp_path / "clip.mp4")
        res = cli_runner(["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "-s", "10", "-d", "20", "-o", out_file], target_func=main)
        assert res.exit_code == 0

    def test_main_invalid_input_exits_with_code_2(self, cli_runner: Callable[..., Any]) -> None:
        """Verify main() exits with code 2 for invalid input source."""
        res = cli_runner(["nonexistent_file_xyz.mp4", "-s", "10", "-e", "20"], target_func=main)
        assert res.exit_code == 2
        assert "Error:" in res.stderr

    def test_cli_main_alias(self, cli_runner: Callable[..., Any]) -> None:
        """Verify cli_main function alias works identically to main."""
        res = cli_runner(["--help"], target_func=cli_main)
        assert res.exit_code == 0
        assert "usage: youtube_clipper" in res.stdout.lower()

    def test_parse_dashboard_and_server_flags(self) -> None:
        """Verify parsing --dashboard, --server, and --port flags."""
        args1 = parse_args(["--dashboard"])
        assert args1.dashboard is True
        assert args1.port == 8080

        args2 = parse_args(["--server", "--port", "9090"])
        assert args2.dashboard is True
        assert args2.port == 9090

    def test_dashboard_mode_validates_without_input(self) -> None:
        """Verify dashboard flag allows missing positional input."""
        args = parse_args(["--dashboard"])
        validated = validate_cli_args(args)
        assert validated.get("dashboard") is True
        assert validated.get("port") == 8080


class TestFolderIdCliFlags:
    """Unit tests for --folder-id and --gdrive-folder flags."""

    def test_parse_folder_id_flags(self) -> None:
        """Verify --folder-id and --gdrive-folder flags parse into folder_id destination."""
        args1 = parse_args(["sample.mp4", "--folder-id", "test_folder_123"])
        args2 = parse_args(["sample.mp4", "--gdrive-folder", "test_folder_456"])
        assert args1.folder_id == "test_folder_123"
        assert args2.folder_id == "test_folder_456"

    def test_validate_cli_args_includes_folder_id(self) -> None:
        """Verify validate_cli_args includes folder_id in returned dictionary."""
        parsed = parse_args(["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "-s", "0", "-e", "10", "--folder-id", "custom_folder_id"])
        validated = validate_cli_args(parsed)
        assert validated.get("folder_id") == "custom_folder_id"

    def test_main_passes_folder_id_to_gdrive_upload(self, monkeypatch: pytest.MonkeyPatch, dummy_video_file: Path) -> None:
        """Verify main() passes folder_id parameter to upload_clip_to_gdrive."""
        captured_kwargs = {}

        def mock_upload(clip_path: str, folder_id: Any = None, **kwargs: Any) -> dict:
            captured_kwargs["clip_path"] = clip_path
            captured_kwargs["folder_id"] = folder_id
            return {"success": True, "web_view_link": "https://drive.google.com/file/d/test"}

        monkeypatch.setattr("youtube_clipper.gdrive_uploader.upload_clip_to_gdrive", mock_upload)

        code = main([str(dummy_video_file), "-s", "0", "-e", "1", "--gdrive", "--folder-id", "target_folder_777"])
        assert code == 0
        assert captured_kwargs.get("folder_id") == "target_folder_777"

    def test_main_returns_failure_when_requested_gdrive_upload_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        dummy_video_file: Path,
        tmp_path: Path,
    ) -> None:
        monkeypatch.setattr(
            "youtube_clipper.pipeline.run_pipeline",
            lambda **_kwargs: str(tmp_path / "clip.mp4"),
        )
        monkeypatch.setattr(
            "youtube_clipper.gdrive_uploader.upload_clip_to_gdrive",
            lambda *_args, **_kwargs: {
                "success": False,
                "error": "quota exceeded",
            },
        )

        code = main(
            [
                str(dummy_video_file),
                "-s",
                "0",
                "-e",
                "1",
                "--gdrive",
            ]
        )
        assert code == 1

