"""
tests/test_e2e_full_pipeline.py - Full programmatic E2E integration test suite.
Verifies complete offline pipeline:
URL -> Subtitle Analysis -> Viral Hook Scoring -> 9:16 Vertical Blur Video Rendering -> GDrive Upload.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest
from youtube_clipper.analyzer import extract_transcript_and_analyze, VideoContentAnalyzer, VTTParser
from youtube_clipper.pipeline import run_pipeline
from youtube_clipper.video_formatter import VideoFormatter
from youtube_clipper.gdrive_uploader import GoogleDriveUploader, upload_clip_to_gdrive


class TestE2EFullProgrammaticPipeline:
    """End-to-end programmatic workflow tests with 100% offline mocking stability."""

    def test_full_e2e_programmatic_flow(
        self,
        mock_yt_dlp_subs: None,
        mock_yt_dlp: pytest.FixtureRequest,
        mock_ffmpeg: pytest.FixtureRequest,
        mock_gdrive: MagicMock,
        tmp_media_dir: Path,
    ) -> None:
        """
        Validates complete programmatic flow:
        1. URL input -> Subtitle analysis & viral hook scoring
        2. Selection of top-ranked clip candidate
        3. Video segment extraction & 9:16 vertical blur rendering
        4. Google Drive upload returning a valid web view URL.
        """
        video_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

        # Step 1: Subtitle Analysis & Viral Hook Scoring
        analysis_result = extract_transcript_and_analyze(video_url)
        assert analysis_result["success"] is True
        assert "clips" in analysis_result
        clips = analysis_result["clips"]
        assert len(clips) > 0

        top_clip = clips[0]
        assert "rank" in top_clip
        assert "score" in top_clip
        assert top_clip["score"] > 0.0
        assert "transcript" in top_clip
        assert "hashtags" in top_clip
        assert len(top_clip["hashtags"]) > 0

        # Step 2: Extract & Render 9:16 Vertical Blur Video
        start_ts = top_clip["start_timestamp"]
        end_ts = top_clip["end_timestamp"]

        rendered_clip_path = run_pipeline(
            input_source=video_url,
            start=start_ts,
            end=end_ts,
            vertical=True,
            output_dir=tmp_media_dir,
        )

        assert rendered_clip_path is not None
        clip_file = Path(rendered_clip_path)
        assert clip_file.exists()
        assert clip_file.stat().st_size > 1000

        # Step 3: Upload rendered clip to Google Drive
        upload_result = upload_clip_to_gdrive(rendered_clip_path)

        assert upload_result["success"] is True
        assert "file_id" in upload_result
        assert upload_result["file_id"] == "file_456"
        assert "web_view_link" in upload_result
        assert "drive.google.com" in upload_result["web_view_link"]

    def test_e2e_video_formatter_crop_center_flow(
        self,
        dummy_video_file: Path,
        tmp_media_dir: Path,
        mock_ffmpeg: pytest.FixtureRequest,
        mock_gdrive: MagicMock,
    ) -> None:
        """
        Validates E2E flow using crop_center format mode:
        Local video input -> 9:16 Center Crop Vertical Rendering -> GDrive Upload.
        """
        out_vertical = str(tmp_media_dir / "crop_center_output.mp4")

        # Render 9:16 center crop
        res_path = VideoFormatter.convert_to_vertical(
            input_path=str(dummy_video_file),
            output_path=out_vertical,
            mode="crop_center",
        )
        assert res_path == out_vertical
        assert Path(out_vertical).exists()
        assert Path(out_vertical).stat().st_size > 1000

        # Upload to GDrive
        uploader = GoogleDriveUploader()
        res = uploader.upload_clip(out_vertical, folder_name="YouTube_Clips")
        assert res["success"] is True
        assert res["file_name"] in ("crop_center_output.mp4", "test_clip.mp4")

    def test_e2e_cli_flow_with_analyze_vertical_and_gdrive_flags(
        self,
        mock_yt_dlp_subs: None,
        mock_yt_dlp: pytest.FixtureRequest,
        mock_ffmpeg: pytest.FixtureRequest,
        mock_gdrive: MagicMock,
        cli_runner: pytest.FixtureRequest,
    ) -> None:
        """
        Validates command-line execution flow with --analyze, --vertical, and --gdrive flags.
        """
        result = cli_runner([
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "-s", "00:00:05",
            "-e", "00:00:35",
            "--vertical",
            "--gdrive",
            "--analyze",
        ])
        assert result.exit_code == 0
        assert "Score" in result.stdout or "Clip" in result.stdout or "Sucesso" in result.stdout or "Drive" in result.stdout
