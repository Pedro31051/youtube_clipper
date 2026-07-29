"""
tests/conftest.py - Shared pytest fixtures for youtube_clipper offline E2E testing.

Fixtures included:
1. tmp_media_dir: Creates and returns a temporary directory Path for media isolation.
2. dummy_video_file: Generates a synthetic sample MP4 video file for testing local processing.
3. mock_yt_dlp: Mocks yt_dlp.YoutubeDL and YouTubeDownloader for offline YouTube downloads.
4. mock_ffmpeg: Mocks FFmpeg subprocess calls and FFmpegProcessor.
5. cli_runner: Invokes youtube_clipper CLI capturing stdout, stderr, exit codes, and exceptions.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generator, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from cortes.log import run_cmd

# Ensure `src` directory is in sys.path for importing youtube_clipper modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


# ---------------------------------------------------------------------------
# Fixture 1: tmp_media_dir
# ---------------------------------------------------------------------------
@pytest.fixture
def tmp_media_dir(tmp_path: Path) -> Path:
    """
    Temporary directory fixture for media input and output files.
    
    Returns:
        Path: Path object pointing to an isolated directory for media operations.
    """
    media_dir = tmp_path / "media_workspace"
    media_dir.mkdir(parents=True, exist_ok=True)
    return media_dir


# ---------------------------------------------------------------------------
# Fixture 2: dummy_video_file
# ---------------------------------------------------------------------------
@pytest.fixture
def dummy_video_file(tmp_media_dir: Path) -> Path:
    """
    Creates a synthetic sample MP4 video file for testing local media processing.
    
    Uses ffmpeg (if available) to generate a valid 2-second MP4 file.
    Falls back to writing a dummy binary file if ffmpeg is unavailable or fails.
    
    Returns:
        Path: Absolute path to the generated synthetic video file.
    """
    video_path = tmp_media_dir / "sample_video.mp4"
    ffmpeg_bin = shutil.which("ffmpeg")
    
    generated_real = False
    if ffmpeg_bin:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-pix_fmt", "yuv420p",
            str(video_path),
        ]
        try:
            res = run_cmd(cmd, audit=False)
            if res.returncode == 0 and video_path.exists() and video_path.stat().st_size > 0:
                generated_real = True
        except Exception:
            generated_real = False

    if not generated_real:
        # Fallback: create synthetic binary content representing a dummy MP4 file
        # Minimal MP4 ftyp box header + dummy payload
        ftyp_box = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        dummy_data = ftyp_box + b"\x00" * 1024
        video_path.write_bytes(dummy_data)
        
    return video_path


# ---------------------------------------------------------------------------
# Fixture 3: mock_yt_dlp
# ---------------------------------------------------------------------------
class MockYTDLPContainer:
    """
    Helper container wrapping mocks for yt_dlp.YoutubeDL and YouTubeDownloader.
    """
    def __init__(self, ytdl_class_mock: MagicMock, downloader_class_mock: Optional[MagicMock] = None):
        self.ytdl_class = ytdl_class_mock
        self.downloader_class = downloader_class_mock
        
        # Instance level mock for yt_dlp.YoutubeDL
        self.ytdl_instance = MagicMock()
        self.ytdl_class.return_value = self.ytdl_instance
        self.ytdl_instance.__enter__.return_value = self.ytdl_instance

        # Default info metadata dictionary returned by extract_info
        self.default_info = {
            "id": "dQw4w9WgXcQ",
            "title": "Synthetic Test Video",
            "duration": 180.0,
            "ext": "mp4",
            "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "formats": [{"format_id": "18", "ext": "mp4", "resolution": "360p"}],
        }
        self.ytdl_instance.extract_info.return_value = self.default_info
        self.ytdl_instance.download.return_value = 0

        def default_extract_info(url: str, download: bool = True) -> Any:
            ret = self.ytdl_instance.extract_info.return_value
            if ret is None:
                return None
            video_id = ret.get("id", "dQw4w9WgXcQ") if isinstance(ret, dict) else "dQw4w9WgXcQ"
            ext = ret.get("ext", "mp4") if isinstance(ret, dict) else "mp4"
            if self.ytdl_class.call_args:
                opts = self.ytdl_class.call_args[0][0]
                outtmpl = opts.get("outtmpl", "")
                if "%(id)s" in outtmpl:
                    out_path = Path(outtmpl.replace("%(id)s", video_id).replace("%(ext)s", ext))
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
            return ret

        self.ytdl_instance.extract_info.side_effect = default_extract_info
        
        # Configure YouTubeDownloader mock instance if present
        if self.downloader_class:
            self.downloader_instance = MagicMock()
            self.downloader_class.return_value = self.downloader_instance
        else:
            self.downloader_instance = None

    def set_extract_info_side_effect(self, side_effect: Any) -> None:
        """Simulate extraction failure or custom behavior in extract_info."""
        self.ytdl_instance.extract_info.side_effect = side_effect

    def set_download_side_effect(self, side_effect: Any) -> None:
        """Simulate download failure or custom behavior in download."""
        self.ytdl_instance.download.side_effect = side_effect


@pytest.fixture
def mock_yt_dlp(tmp_media_dir: Path) -> Generator[MockYTDLPContainer, None, None]:
    """
    Mock fixture for yt_dlp.YoutubeDL and YouTubeDownloader.
    
    Prevents external network calls during test execution while providing realistic
    download simulation and hooks for error testing.
    """
    # Create patches
    ytdl_patcher = patch("yt_dlp.YoutubeDL")
    mock_ytdl_class = ytdl_patcher.start()

    # Try patching youtube_clipper.downloader.YouTubeDownloader if available
    downloader_patcher = None
    mock_downloader_class = None
    try:
        import youtube_clipper.downloader  # type: ignore
        downloader_patcher = patch("youtube_clipper.downloader.YouTubeDownloader")
        mock_downloader_class = downloader_patcher.start()
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass

    container = MockYTDLPContainer(mock_ytdl_class, mock_downloader_class)

    # Setup side effect on download_segment or download to create output file if requested
    if container.downloader_instance:
        def default_download_segment(url: str, start: float, end: float, output_dir: str | Path, **kwargs: Any) -> str:
            out_path = Path(output_dir) / "yt_downloaded_segment.mp4"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if not out_path.exists():
                out_path.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 512)
            return str(out_path)

        container.downloader_instance.download_segment.side_effect = default_download_segment

    yield container

    ytdl_patcher.stop()
    if downloader_patcher:
        downloader_patcher.stop()


# ---------------------------------------------------------------------------
# Fixture 4: mock_ffmpeg
# ---------------------------------------------------------------------------
class MockFFmpegContainer:
    """
    Helper container wrapping mocks for FFmpeg subprocess calls and FFmpegProcessor.
    """
    def __init__(
        self,
        subprocess_run_mock: MagicMock,
        subprocess_popen_mock: MagicMock,
        which_mock: MagicMock,
        processor_class_mock: Optional[MagicMock] = None,
    ):
        self.run = subprocess_run_mock
        self.popen = subprocess_popen_mock
        self.which = which_mock
        self.processor_class = processor_class_mock
        
        # Configure default which return value
        self.which.return_value = "/usr/bin/ffmpeg"
        
        # Default completed process return value for subprocess.run
        self.default_completed = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=0, stdout="ffmpeg version 4.4", stderr=""
        )
        self.last_media_duration = 2.0
        
        # Define smart subprocess.run side effect that auto-creates output file if requested in cmd
        def smart_run(cmd: List[str] | str, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
            cmd_list = cmd if isinstance(cmd, list) else [str(cmd)]
            cmd_str = " ".join(cmd_list)

            if cmd_list and Path(cmd_list[0]).name == "ffprobe":
                return subprocess.CompletedProcess(
                    args=cmd,
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "format": {"duration": str(self.last_media_duration)},
                            "streams": [{"codec_type": "video", "width": 1080, "height": 1920}],
                        }
                    ),
                    stderr="",
                )

            if isinstance(cmd, list) and cmd_list and Path(cmd_list[0]).name == "ffmpeg":
                if "-t" in cmd_list:
                    try:
                        self.last_media_duration = float(
                            cmd_list[cmd_list.index("-t") + 1]
                        )
                    except (ValueError, IndexError):
                        pass

            # Handle yt-dlp --write-auto-subs subtitle generation
            if ("yt-dlp" in cmd_str or "yt_dlp" in cmd_str) and "--write-auto-subs" in cmd_str:
                out_tmpl = None
                if isinstance(cmd, list) and "-o" in cmd:
                    idx = cmd.index("-o")
                    if idx + 1 < len(cmd):
                        out_tmpl = cmd[idx + 1]
                if out_tmpl:
                    vtt_path = Path(f"{out_tmpl}.pt.vtt")
                    vtt_path.parent.mkdir(parents=True, exist_ok=True)
                    vtt_content = (
                        "WEBVTT\n\n"
                        "00:00:01.000 --> 00:00:05.000\n"
                        "Você sabia que este é um segredo incrível revelado?\n\n"
                        "00:00:06.000 --> 00:00:35.000\n"
                        "Como isto funciona na prática? Veja os detalhes surpreendentes da história.\n\n"
                        "00:00:36.000 --> 00:01:05.000\n"
                        "Por que esta descoberta é tão importante? Entenda o resultado final incrível.\n"
                    )
                    vtt_path.write_text(vtt_content, encoding="utf-8")
                return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

            if isinstance(cmd, list):
                # Look for output file argument (usually the last argument or after options)
                if len(cmd) > 1 and not cmd[-1].startswith("-"):
                    out_candidate = Path(cmd[-1])
                    if out_candidate.parent.exists():
                        try:
                            if not out_candidate.exists():
                                out_candidate.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)
                        except Exception:
                            pass
            return self.default_completed

        self.run.side_effect = smart_run

        if self.processor_class:
            self.processor_instance = MagicMock()
            self.processor_class.return_value = self.processor_instance
            
            def default_cut_media(input_path: str, start: float, end: float, output_path: str, fast_copy: bool = False) -> str:
                out_p = Path(output_path)
                out_p.parent.mkdir(parents=True, exist_ok=True)
                if not out_p.exists():
                    out_p.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048)
                return str(out_p)

            self.processor_instance.cut_media.side_effect = default_cut_media
        else:
            self.processor_instance = None

    def simulate_missing_ffmpeg(self) -> None:
        """Simulate system where ffmpeg binary is not found."""
        self.which.return_value = None
        self.run.side_effect = FileNotFoundError("No such file or directory: 'ffmpeg'")

    def simulate_failure(self, returncode: int = 1, stderr: str = "FFmpeg error occurred") -> None:
        """Simulate FFmpeg command execution failure."""
        failed_proc = subprocess.CompletedProcess(
            args=["ffmpeg"], returncode=returncode, stdout="", stderr=stderr
        )
        self.run.side_effect = None
        self.run.return_value = failed_proc
        if self.processor_instance:
            self.processor_instance.cut_media.side_effect = Exception(stderr)

    @property
    def last_command(self) -> Optional[List[str]]:
        """Return the last FFmpeg command, excluding the validation ffprobe call."""
        for call in reversed(self.run.call_args_list):
            call_args = call[0]
            if call_args and isinstance(call_args[0], list):
                command = call_args[0]
                if command and Path(command[0]).name.startswith("ffmpeg"):
                    return command
        return None

    def has_arg(self, arg: str) -> bool:
        """Check if a specific argument was present in the last subprocess.run call."""
        last_cmd = self.last_command
        return arg in last_cmd if last_cmd else False


@pytest.fixture
def mock_ffmpeg() -> Generator[MockFFmpegContainer, None, None]:
    """
    Mock fixture for FFmpeg subprocess calls and FFmpegProcessor.
    
    Intercepts subprocess executions of ffmpeg and provides controls for simulating
    missing binary, failed command executions, and verifying CLI flag generation.
    """
    run_patcher = patch("subprocess.run")
    popen_patcher = patch("subprocess.Popen")
    which_patcher = patch("shutil.which")

    mock_run = run_patcher.start()
    mock_popen = popen_patcher.start()
    mock_which = which_patcher.start()

    processor_patcher = None
    mock_processor_class = None
    try:
        import youtube_clipper.processor  # type: ignore
        processor_patcher = patch("youtube_clipper.processor.FFmpegProcessor")
        mock_processor_class = processor_patcher.start()
    except (ImportError, ModuleNotFoundError, AttributeError):
        pass

    container = MockFFmpegContainer(mock_run, mock_popen, mock_which, mock_processor_class)

    yield container

    run_patcher.stop()
    popen_patcher.stop()
    which_patcher.stop()
    if processor_patcher:
        processor_patcher.stop()


# ---------------------------------------------------------------------------
# Fixture 4b: isolate_cwd_for_tests
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolate_cwd_for_tests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate current working directory to tmp_path for all test executions."""
    monkeypatch.chdir(tmp_path)


# ---------------------------------------------------------------------------
# Fixture 5: cli_runner
# ---------------------------------------------------------------------------
@dataclass
class CLIRunnerResult:
    """Result container for cli_runner invocations."""
    exit_code: int
    stdout: str
    stderr: str
    exception: Optional[BaseException] = None


@pytest.fixture
def cli_runner() -> Callable[..., CLIRunnerResult]:
    """
    Helper fixture to invoke the youtube_clipper CLI / cli.py / __main__.py.
    
    Captures stdout, stderr, exit codes, and exceptions without causing
    pytest to fail on SystemExit.
    
    Returns:
        Callable: Function run_cli(args, ...) -> CLIRunnerResult
    """
    import shlex

    def run_cli(args: str | List[str], target_func: Optional[Callable[..., Any]] = None) -> CLIRunnerResult:
        if isinstance(args, str):
            args_list = shlex.split(args)
        else:
            args_list = list(args)

        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()
        exit_code = 0
        captured_exception: Optional[BaseException] = None

        # Determine target function if not explicitly provided
        func_to_call = target_func
        if func_to_call is None:
            try:
                import youtube_clipper.cli as ytc_cli
                if hasattr(ytc_cli, "main"):
                    func_to_call = ytc_cli.main
                elif hasattr(ytc_cli, "cli_main"):
                    func_to_call = ytc_cli.cli_main
            except (ImportError, ModuleNotFoundError):
                pass

        # Save previous sys.argv
        old_argv = sys.argv
        sys.argv = ["youtube_clipper"] + args_list

        try:
            with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
                if func_to_call is not None:
                    res_code = func_to_call()
                    if isinstance(res_code, int):
                        exit_code = res_code
                else:
                    # Fallback if module is not yet implemented
                    raise NotImplementedError("youtube_clipper CLI main entrypoint is not yet implemented.")
        except SystemExit as e:
            if isinstance(e.code, int):
                exit_code = e.code
            elif e.code is None:
                exit_code = 0
            else:
                exit_code = 1
                print(str(e.code), file=captured_stderr)
        except BaseException as e:
            exit_code = 1
            captured_exception = e
        finally:
            sys.argv = old_argv

        return CLIRunnerResult(
            exit_code=exit_code,
            stdout=captured_stdout.getvalue(),
            stderr=captured_stderr.getvalue(),
            exception=captured_exception,
        )

    return run_cli


# ---------------------------------------------------------------------------
# Fixture 6: mock_gdrive
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_gdrive(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> MagicMock:
    """
    Fixture mocking Google Drive Service Account auth, discovery build, files.list,
    files.create, permissions.create, and MediaFileUpload.
    """
    mock_service = MagicMock()
    mock_files = MagicMock()
    mock_permissions = MagicMock()

    mock_files.list().execute.return_value = {
        "files": [{"id": "folder_123", "name": "YouTube_Clips"}]
    }

    create_req_mock = MagicMock()
    def default_create_execute() -> dict[str, Any]:
        args, kwargs = mock_files.create.call_args if mock_files.create.call_args else ((), {})
        body = kwargs.get("body") if "body" in kwargs else (args[0] if args else {})
        file_name = body.get("name", "test_clip.mp4") if isinstance(body, dict) else "test_clip.mp4"
        return {
            "id": "file_456",
            "name": file_name,
            "webViewLink": "https://drive.google.com/file/d/file_456/view",
            "webContentLink": "https://drive.google.com/uc?id=file_456",
            "size": "1048576"
        }
    create_req_mock.execute.side_effect = default_create_execute
    mock_files.create.return_value = create_req_mock

    mock_permissions.create().execute.return_value = {"id": "perm_789"}

    mock_service.files.return_value = mock_files
    mock_service.permissions.return_value = mock_permissions

    mock_creds = MagicMock()
    mock_creds.universe_domain = "googleapis.com"
    mock_creds.create_scoped.return_value = mock_creds
    mock_creds.with_scopes.return_value = mock_creds
    mock_creds.authorize.return_value = mock_creds
    mock_creds.credentials = mock_creds
    monkeypatch.setattr(
        "google.oauth2.service_account.Credentials.from_service_account_file",
        lambda path, scopes: mock_creds
    )
    monkeypatch.setattr(
        "googleapiclient.discovery.build",
        lambda service_name, version, credentials=None, **kwargs: mock_service
    )

    dummy_sa_file = tmp_path / "service-account.json"
    dummy_sa_file.write_text('{"type": "service_account", "project_id": "test-project"}')

    try:
        import youtube_clipper.gdrive_uploader as gdu
        monkeypatch.setattr(gdu, "MediaFileUpload", MagicMock())
        monkeypatch.setattr(gdu, "build", lambda service_name, version, credentials=None, **kwargs: mock_service)
        monkeypatch.setattr(gdu, "DEFAULT_SERVICE_ACCOUNT_PATH", str(dummy_sa_file))
    except (ImportError, AttributeError):
        pass

    return mock_service


# ---------------------------------------------------------------------------
# Fixture 7: mock_yt_dlp_subs
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_yt_dlp_subs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[None, None, None]:
    """
    Mocks the audited command gateway for yt-dlp subtitle generation.
    """
    def mock_analyzer_run_cmd(
        cmd: Any, *args: Any, **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        cmd_list = cmd if isinstance(cmd, list) else [str(cmd)]
        cmd_str = " ".join(cmd_list)

        if ("yt-dlp" in cmd_str or "yt_dlp" in cmd_str) and "--write-auto-subs" in cmd_str:
            out_tmpl = None
            if isinstance(cmd, list) and "-o" in cmd:
                idx = cmd.index("-o")
                if idx + 1 < len(cmd):
                    out_tmpl = cmd[idx + 1]
            if not out_tmpl:
                out_tmpl = str(tmp_path / "subtitle")

            vtt_path = Path(f"{out_tmpl}.pt.vtt")
            vtt_path.parent.mkdir(parents=True, exist_ok=True)
            vtt_content = (
                "WEBVTT\n\n"
                "00:00:01.000 --> 00:00:05.000\n"
                "Você sabia que este é um segredo incrível revelado?\n\n"
                "00:00:06.000 --> 00:00:35.000\n"
                "Como isto funciona na prática? Veja os detalhes surpreendentes da história.\n\n"
                "00:00:36.000 --> 00:01:05.000\n"
                "Por que esta descoberta é tão importante? Entenda o resultado final incrível.\n"
            )
            vtt_path.write_text(vtt_content, encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

        return run_cmd(cmd, *args, **kwargs)

    monkeypatch.setattr(
        "youtube_clipper.analyzer.run_cmd",
        mock_analyzer_run_cmd,
    )
    yield


# ---------------------------------------------------------------------------
# Fixture 8: dashboard_server
# ---------------------------------------------------------------------------
from http.server import HTTPServer
from socketserver import ThreadingMixIn
import threading
import json
from youtube_clipper.web_dashboard import ClipperDashboardHandler, extract_transcript_and_analyze, run_pipeline, upload_clip_to_gdrive


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


@pytest.fixture
def dashboard_server() -> Generator[str, None, None]:
    """
    Launches ThreadingHTTPServer on an ephemeral port (127.0.0.1:0) in a background
    daemon thread, returning base URL `http://127.0.0.1:{port}`, and closing server cleanly on teardown.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), ClipperDashboardHandler)
    server.output_dir = (Path.cwd() / "media_workspace").resolve()
    server.output_dir.mkdir(parents=True, exist_ok=True)
    server.api_token = None
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()
