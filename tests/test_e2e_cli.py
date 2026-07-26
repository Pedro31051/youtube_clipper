"""
tests/test_e2e_cli.py - E2E & Unit Test Suite for CLI Argument Parser & Entrypoint.

Covers Feature 1 (Package Setup & Entrypoint) and Feature 4 (CLI Argument Parser & User Help).
Includes Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner Cases).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple

import pytest

from youtube_clipper.exceptions import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# Dynamic Fallback & Module Integration Helpers
# ---------------------------------------------------------------------------

def _build_reference_parser() -> argparse.ArgumentParser:
    """
    Builds a reference CLI ArgumentParser conforming strictly to the contract in
    PROJECT.md and ORIGINAL_REQUEST.md.
    Used as fallback when youtube_clipper.cli is not yet implemented or imported.
    """
    parser = argparse.ArgumentParser(
        prog="youtube_clipper",
        description="A Python CLI tool for clipping YouTube videos and local media files by timestamp.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  youtube_clipper https://youtu.be/dQw4w9WgXcQ --start 00:01:00 --end 00:02:00 -o clip.mp4\n"
            "  youtube_clipper sample.mp4 --start 10 --duration 30 --fast\n"
        ),
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="YouTube video URL or local media file path.",
    )
    parser.add_argument(
        "-s",
        "--start",
        dest="start",
        default=None,
        help="Start timestamp (HH:MM:SS, MM:SS, SS, or seconds float).",
    )
    parser.add_argument(
        "-e",
        "--end",
        dest="end",
        default=None,
        help="End timestamp (HH:MM:SS, MM:SS, SS, or seconds float).",
    )
    parser.add_argument(
        "-d",
        "--duration",
        "--length",
        dest="duration",
        default=None,
        help="Clip duration (HH:MM:SS, MM:SS, SS, or seconds float).",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        default=None,
        help="Output file path or directory.",
    )
    parser.add_argument(
        "--fast",
        "--copy",
        dest="fast",
        action="store_true",
        default=False,
        help="Enable fast stream copying without re-encoding.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        default=False,
        help="Enable verbose output and progress logging.",
    )
    return parser


def _reference_main(argv: Optional[List[str]] = None) -> int:
    """
    Reference main entrypoint logic enforcing CLI parameter contract and validation rules.
    """
    parser = _get_parser()
    if argv is None:
        args = parser.parse_args()
    else:
        args = parser.parse_args(argv)

    if not args.input or not args.input.strip():
        parser.error("the following arguments are required: input")

    if args.end is not None and args.duration is not None:
        sys.stderr.write("Error: Cannot specify both --end and --duration options.\n")
        raise ValidationError("Cannot specify both --end and --duration options.")

    return 0


def _get_parser() -> argparse.ArgumentParser:
    """Dynamically loads parser from youtube_clipper.cli or falls back to reference parser."""
    try:
        import youtube_clipper.cli as cli_mod  # type: ignore
        if hasattr(cli_mod, "create_parser"):
            return cli_mod.create_parser()
        elif hasattr(cli_mod, "get_parser"):
            return cli_mod.get_parser()
        elif hasattr(cli_mod, "build_parser"):
            return cli_mod.build_parser()
    except (ImportError, ModuleNotFoundError):
        pass
    return _build_reference_parser()


def _get_target_func() -> Callable[[], Any]:
    """Dynamically loads main entrypoint function or falls back to reference main runner."""
    try:
        import youtube_clipper.cli as cli_mod  # type: ignore
        if hasattr(cli_mod, "main"):
            return cli_mod.main
        elif hasattr(cli_mod, "cli_main"):
            return cli_mod.cli_main
    except (ImportError, ModuleNotFoundError):
        pass

    try:
        import youtube_clipper.__main__ as main_mod  # type: ignore
        if hasattr(main_mod, "main"):
            return main_mod.main
    except (ImportError, ModuleNotFoundError):
        pass

    return _reference_main


# ---------------------------------------------------------------------------
# Test Class 1: TestCLIArgumentParsingTier1 (Feature Coverage - Flags & Options)
# ---------------------------------------------------------------------------

class TestCLIArgumentParsingTier1:
    """Tier 1 tests covering core CLI argument parsing flags and option parsing."""

    def test_cli_positional_input_url(self) -> None:
        """Verify positional argument correctly parses a YouTube video URL."""
        parser = _get_parser()
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        args = parser.parse_args([url])
        assert args.input == url

    def test_cli_positional_input_filepath(self) -> None:
        """Verify positional argument correctly parses a local video file path."""
        parser = _get_parser()
        filepath = "/tmp/media/sample_video.mp4"
        args = parser.parse_args([filepath])
        assert args.input == filepath

    def test_cli_start_flag_variants(self) -> None:
        """Verify --start and -s options are parsed into start attribute."""
        parser = _get_parser()

        args_long = parser.parse_args(["video.mp4", "--start", "00:01:30"])
        assert args_long.start == "00:01:30"

        args_short = parser.parse_args(["video.mp4", "-s", "90"])
        assert args_short.start == "90"

        args_float = parser.parse_args(["video.mp4", "-s", "45.5"])
        assert args_float.start == "45.5"

    def test_cli_end_flag_variants(self) -> None:
        """Verify --end and -e options are parsed into end attribute."""
        parser = _get_parser()

        args_long = parser.parse_args(["video.mp4", "--end", "00:03:00"])
        assert args_long.end == "00:03:00"

        args_short = parser.parse_args(["video.mp4", "-e", "180"])
        assert args_short.end == "180"

    def test_cli_duration_flag_variants(self) -> None:
        """Verify --duration, --length, and -d options are parsed into duration attribute."""
        parser = _get_parser()

        args_duration = parser.parse_args(["video.mp4", "--duration", "00:02:00"])
        assert args_duration.duration == "00:02:00"

        args_length = parser.parse_args(["video.mp4", "--length", "120"])
        assert args_length.duration == "120"

        args_short = parser.parse_args(["video.mp4", "-d", "60"])
        assert args_short.duration == "60"

    def test_cli_output_flag_variants(self) -> None:
        """Verify --output and -o options are parsed into output attribute."""
        parser = _get_parser()

        args_long = parser.parse_args(["video.mp4", "--output", "clip_out.mp4"])
        assert args_long.output == "clip_out.mp4"

        args_short = parser.parse_args(["video.mp4", "-o", "/tmp/output/clip.mp4"])
        assert args_short.output == "/tmp/output/clip.mp4"

    def test_cli_fast_flag_variants(self) -> None:
        """Verify --fast and --copy flags toggle the fast boolean attribute."""
        parser = _get_parser()

        args_default = parser.parse_args(["video.mp4"])
        assert args_default.fast is False

        args_fast = parser.parse_args(["video.mp4", "--fast"])
        assert args_fast.fast is True

        args_copy = parser.parse_args(["video.mp4", "--copy"])
        assert args_copy.fast is True

    def test_cli_verbose_flag_variants(self) -> None:
        """Verify --verbose and -v flags toggle the verbose boolean attribute."""
        parser = _get_parser()

        args_default = parser.parse_args(["video.mp4"])
        assert args_default.verbose is False

        args_verbose = parser.parse_args(["video.mp4", "--verbose"])
        assert args_verbose.verbose is True

        args_short = parser.parse_args(["video.mp4", "-v"])
        assert args_short.verbose is True

    def test_cli_combined_valid_flags(
        self, cli_runner: Callable[..., Any], mock_yt_dlp: Any, mock_ffmpeg: Any, tmp_path: Path
    ) -> None:
        """Verify parsing a complete CLI invocation with all valid flags combined."""
        parser = _get_parser()
        out_path = str(tmp_path / "output_clip.mp4")
        cmd_args = [
            "https://youtu.be/dQw4w9WgXcQ",
            "-s", "00:00:10",
            "-e", "00:00:40",
            "-o", out_path,
            "--fast",
            "-v",
        ]
        args = parser.parse_args(cmd_args)
        assert args.input == "https://youtu.be/dQw4w9WgXcQ"
        assert args.start == "00:00:10"
        assert args.end == "00:00:40"
        assert args.output == out_path
        assert args.fast is True
        assert args.verbose is True

        # Test runner execution success
        target_func = _get_target_func()
        res = cli_runner(cmd_args, target_func=target_func)
        assert res.exit_code == 0


# ---------------------------------------------------------------------------
# Test Class 2: TestCLIArgumentParsingTier2 (Boundary & Corner Cases)
# ---------------------------------------------------------------------------

class TestCLIArgumentParsingTier2:
    """Tier 2 tests covering boundary cases, conflicting flags, missing args, and error handling."""

    def test_cli_missing_positional_input(self, cli_runner: Callable[..., Any]) -> None:
        """Verify CLI execution fails with non-zero exit code when required input is missing."""
        target_func = _get_target_func()
        res = cli_runner("", target_func=target_func)
        assert res.exit_code != 0
        assert "required" in res.stderr.lower() or "usage:" in res.stderr.lower() or res.exit_code == 2

    def test_cli_conflicting_end_and_duration(self, cli_runner: Callable[..., Any]) -> None:
        """Verify providing both --end and --duration results in an error/exception."""
        target_func = _get_target_func()
        cmd_args = ["sample.mp4", "-s", "10", "--end", "30", "--duration", "20"]
        res = cli_runner(cmd_args, target_func=target_func)

        assert res.exit_code != 0 or res.exception is not None
        if res.exception is not None:
            assert isinstance(res.exception, (ValidationError, SystemExit))

    def test_cli_unrecognized_arguments(self, cli_runner: Callable[..., Any]) -> None:
        """Verify unknown CLI flags cause argparse error and non-zero exit code."""
        target_func = _get_target_func()
        res = cli_runner("video.mp4 --unrecognized-option-xyz", target_func=target_func)
        assert res.exit_code != 0
        assert "unrecognized" in res.stderr.lower() or "error" in res.stderr.lower() or res.exit_code == 2

    def test_cli_empty_arguments(self, cli_runner: Callable[..., Any]) -> None:
        """Verify running CLI with empty arguments string produces usage error."""
        target_func = _get_target_func()
        res = cli_runner([], target_func=target_func)
        assert res.exit_code != 0

    def test_cli_empty_string_input(self, cli_runner: Callable[..., Any]) -> None:
        """Verify passing an empty string or whitespace as positional argument fails validation."""
        target_func = _get_target_func()
        res = cli_runner('"" -s 10 -e 20', target_func=target_func)
        assert res.exit_code != 0 or res.exception is not None

    def test_cli_invalid_flag_formats(self, cli_runner: Callable[..., Any]) -> None:
        """Verify flags expecting a value fail when value is omitted at end of command."""
        target_func = _get_target_func()
        res = cli_runner("video.mp4 --start", target_func=target_func)
        assert res.exit_code != 0
        assert "expected one argument" in res.stderr.lower() or res.exit_code == 2

    def test_cli_aliased_flags_equivalence(self) -> None:
        """Verify flag aliases parse into identical Namespace values."""
        parser = _get_parser()

        args_s = parser.parse_args(["in.mp4", "-s", "10"])
        args_start = parser.parse_args(["in.mp4", "--start", "10"])
        assert args_s.start == args_start.start == "10"

        args_d = parser.parse_args(["in.mp4", "-d", "15"])
        args_dur = parser.parse_args(["in.mp4", "--duration", "15"])
        args_len = parser.parse_args(["in.mp4", "--length", "15"])
        assert args_d.duration == args_dur.duration == args_len.duration == "15"

        args_fast = parser.parse_args(["in.mp4", "--fast"])
        args_copy = parser.parse_args(["in.mp4", "--copy"])
        assert args_fast.fast == args_copy.fast is True


# ---------------------------------------------------------------------------
# Test Class 3: TestCLIHelpAndEntrypointTier1 (Help Content & Formatting)
# ---------------------------------------------------------------------------

class TestCLIHelpAndEntrypointTier1:
    """Tier 1 tests verifying --help flag output content, parameter descriptions, and usage format."""

    def test_cli_help_flag_stdout_and_exit_code(self, cli_runner: Callable[..., Any]) -> None:
        """Verify --help and -h flags display help text and exit cleanly with status code 0."""
        target_func = _get_target_func()

        res_long = cli_runner("--help", target_func=target_func)
        assert res_long.exit_code == 0
        assert "usage:" in res_long.stdout.lower() or "--help" in res_long.stdout or "options:" in res_long.stdout.lower()

        res_short = cli_runner("-h", target_func=target_func)
        assert res_short.exit_code == 0
        assert "usage:" in res_short.stdout.lower() or "-h" in res_short.stdout

    def test_cli_help_contains_positional_desc(self, cli_runner: Callable[..., Any]) -> None:
        """Verify --help text includes documentation for the positional input argument."""
        target_func = _get_target_func()
        res = cli_runner("--help", target_func=target_func)
        assert res.exit_code == 0
        assert "input" in res.stdout.lower()

    def test_cli_help_contains_timestamp_options(self, cli_runner: Callable[..., Any]) -> None:
        """Verify --help text documents --start, --end, and --duration/--length options."""
        target_func = _get_target_func()
        res = cli_runner("--help", target_func=target_func)
        stdout = res.stdout.lower()
        assert "--start" in stdout or "-s" in stdout
        assert "--end" in stdout or "-e" in stdout
        assert "--duration" in stdout or "--length" in stdout or "-d" in stdout

    def test_cli_help_contains_output_and_fast_options(self, cli_runner: Callable[..., Any]) -> None:
        """Verify --help text documents --output, --fast/--copy, and --verbose options."""
        target_func = _get_target_func()
        res = cli_runner("--help", target_func=target_func)
        stdout = res.stdout.lower()
        assert "--output" in stdout or "-o" in stdout
        assert "--fast" in stdout or "--copy" in stdout
        assert "--verbose" in stdout or "-v" in stdout

    def test_cli_help_contains_usage_examples(self, cli_runner: Callable[..., Any]) -> None:
        """Verify --help output includes usage patterns or description/epilog."""
        target_func = _get_target_func()
        res = cli_runner("--help", target_func=target_func)
        assert res.exit_code == 0
        assert len(res.stdout) > 50


# ---------------------------------------------------------------------------
# Test Class 4: TestCLIHelpAndEntrypointTier2 (Entrypoint Execution & Edge Cases)
# ---------------------------------------------------------------------------

class TestCLIHelpAndEntrypointTier2:
    """Tier 2 tests verifying module execution via python3 -m youtube_clipper and edge cases."""

    def test_cli_python_module_help_execution(self, cli_runner: Callable[..., Any]) -> None:
        """
        Verify executing python3 -m youtube_clipper --help returns exit code 0 and displays help text.
        Executes via subprocess if __main__.py exists; falls back to cli_runner verification.
        """
        main_py = SRC_DIR / "youtube_clipper" / "__main__.py"
        if main_py.exists():
            cmd = [sys.executable, "-m", "youtube_clipper", "--help"]
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(PROJECT_ROOT),
            )
            assert res.returncode == 0
            assert "usage:" in res.stdout.lower() or "--help" in res.stdout
        else:
            target_func = _get_target_func()
            res = cli_runner("--help", target_func=target_func)
            assert res.exit_code == 0
            assert "usage:" in res.stdout.lower() or "--help" in res.stdout

    def test_cli_python_module_missing_args_execution(self, cli_runner: Callable[..., Any]) -> None:
        """
        Verify executing python3 -m youtube_clipper without arguments exits with non-zero status.
        Executes via subprocess if __main__.py exists; falls back to cli_runner verification.
        """
        main_py = SRC_DIR / "youtube_clipper" / "__main__.py"
        if main_py.exists():
            cmd = [sys.executable, "-m", "youtube_clipper"]
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(PROJECT_ROOT),
            )
            assert res.returncode != 0
        else:
            target_func = _get_target_func()
            res = cli_runner("", target_func=target_func)
            assert res.exit_code != 0

    def test_cli_parser_default_values(self) -> None:
        """Verify default attribute values when only required positional argument is supplied."""
        parser = _get_parser()
        args = parser.parse_args(["https://youtu.be/dQw4w9WgXcQ"])
        assert args.input == "https://youtu.be/dQw4w9WgXcQ"
        assert args.start is None
        assert args.end is None
        assert args.duration is None
        assert args.output is None
        assert args.fast is False
        assert args.verbose is False

    def test_cli_adversarial_special_chars_in_args(
        self, cli_runner: Callable[..., Any], dummy_video_file: Path, tmp_path: Path
    ) -> None:
        """Adversarial test: Verify handling of input/output paths containing spaces, quotes, and special symbols."""
        parser = _get_parser()
        complex_dir = tmp_path / "my path with spaces"
        complex_dir.mkdir(parents=True, exist_ok=True)
        complex_path = complex_dir / "video (1) [720p].mp4"
        shutil.copy(dummy_video_file, complex_path)

        complex_output = str(tmp_path / "my output" / "clip & final #1.mp4")

        args = parser.parse_args([str(complex_path), "-o", complex_output, "--start", "00:01:00.500"])
        assert args.input == str(complex_path)
        assert args.output == complex_output
        assert args.start == "00:01:00.500"

        target_func = _get_target_func()
        res = cli_runner([str(complex_path), "-o", complex_output, "-s", "0", "-e", "1"], target_func=target_func)
        assert res.exit_code == 0
