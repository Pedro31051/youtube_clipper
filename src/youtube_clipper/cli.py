"""CLI Argument Parser & Entrypoint module for youtube_clipper.

Provides ClipperArgumentParser, argument parsing, CLI validation,
AI analysis triggers, Google Drive integration, Cookies management, and top-level entrypoints main() / cli_main().
"""

from __future__ import annotations

import argparse
import sys
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from youtube_clipper.exceptions import ClipperError, ValidationError
from youtube_clipper.validator import is_youtube_url, validate_input_source, validate_time_range


class ClipperArgumentParser(argparse.ArgumentParser):
    """Custom ArgumentParser providing clean error formatting and exit code 2."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"{self.prog}: error: {message}\n")
        sys.exit(2)


def create_parser() -> argparse.ArgumentParser:
    """Build and return the ArgumentParser instance for youtube_clipper."""
    parser = ClipperArgumentParser(
        prog="youtube_clipper",
        description="A Python CLI tool for AI-powered clipping, analysis, and Google Drive upload of YouTube videos.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  youtube_clipper https://youtu.be/dQw4w9WgXcQ --start 00:01:00 --end 00:02:00 -o clip.mp4\n"
            "  youtube_clipper https://youtu.be/3Vpf3EaE1mc --analyze\n"
            "  youtube_clipper sample.mp4 --start 10 --duration 30 --vertical --gdrive\n"
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
        "--vertical",
        "--shorts",
        dest="vertical",
        action="store_true",
        default=False,
        help="Convert clip output into 9:16 vertical video layout for Shorts/Reels/TikTok.",
    )
    parser.add_argument(
        "--gdrive",
        "--upload-gdrive",
        dest="gdrive",
        action="store_true",
        default=False,
        help="Automatically upload the generated clip to Google Drive via MCP / Service Account.",
    )
    parser.add_argument(
        "--folder-id",
        "--gdrive-folder",
        dest="folder_id",
        default=None,
        help="Target Google Drive folder ID for clip uploads (defaults to 1mYLUnTMhdflzmYhee804Nj52jBQuOI8H).",
    )
    parser.add_argument(
        "--cookies",
        dest="cookies",
        default=None,
        help="Path to cookies.txt file or browser name (e.g. chrome, firefox) for YouTube botguard bypass.",
    )
    parser.add_argument(
        "--analyze",
        dest="analyze",
        action="store_true",
        default=False,
        help="Run AI content analysis on YouTube transcript to identify viral hook moments.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        default=False,
        help="Enable verbose output and progress logging.",
    )
    parser.add_argument(
        "--dashboard",
        "--server",
        dest="dashboard",
        action="store_true",
        default=False,
        help="Launch the web dashboard UI server.",
    )
    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        default=8080,
        help="Port number for the web dashboard server (default: 8080).",
    )
    parser.add_argument(
        "--host",
        dest="host",
        default="127.0.0.1",
        help="Dashboard bind address (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--api-token",
        dest="api_token",
        default=None,
        help="Bearer token required when exposing the dashboard beyond loopback.",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        default=None,
        help="Dedicated dashboard directory for generated and downloadable clips.",
    )
    return parser


get_parser = create_parser
build_parser = create_parser


def parse_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = create_parser()
    parsed = parser.parse_args(args)

    if not getattr(parsed, "dashboard", False) and (not parsed.input or not parsed.input.strip()):
        parser.error("the following arguments are required: input")

    has_end = parsed.end is not None and bool(str(parsed.end).strip())
    has_duration = parsed.duration is not None and bool(str(parsed.duration).strip())

    if has_end and has_duration:
        raise ValidationError("Cannot specify both --end and --duration options.", field="time_range")

    return parsed


def validate_cli_args(args: argparse.Namespace) -> Dict[str, Any]:
    if getattr(args, "dashboard", False):
        return {
            "dashboard": True,
            "port": getattr(args, "port", 8080) or 8080,
            "host": getattr(args, "host", "127.0.0.1"),
            "api_token": getattr(args, "api_token", None),
            "output_dir": getattr(args, "output_dir", None),
        }

    clean_input = validate_input_source(args.input)
    
    if getattr(args, "analyze", False):
        start_sec, end_sec = 0.0, 0.0
    else:
        start_sec, end_sec = validate_time_range(args.start, args.end, args.duration)

    return {
        "input": clean_input,
        "start": start_sec,
        "end": end_sec,
        "output": args.output,
        "fast": args.fast,
        "vertical": getattr(args, "vertical", False),
        "gdrive": getattr(args, "gdrive", False),
        "folder_id": getattr(args, "folder_id", None),
        "cookies": getattr(args, "cookies", None),
        "analyze": getattr(args, "analyze", False),
        "verbose": args.verbose,
    }


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    try:
        parsed = parse_args(argv)
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return 0 if exc.code is None else 1
    except ValidationError as exc:
        sys.stderr.write(f"Error: {exc.message}\n")
        return exc.exit_code
    except ClipperError as exc:
        sys.stderr.write(f"Error: {exc.message}\n")
        return exc.exit_code

    try:
        validated = validate_cli_args(parsed)

        if getattr(parsed, "dashboard", False):
            port = getattr(parsed, "port", 8080) or 8080
            sys.stdout.write(f"🚀 Launching YouTube Clipper Web Dashboard on http://localhost:{port}...\n")
            from youtube_clipper.web_dashboard import start_dashboard_server
            start_dashboard_server(
                port=port,
                host=getattr(parsed, "host", "127.0.0.1"),
                api_token=getattr(parsed, "api_token", None),
                output_dir=getattr(parsed, "output_dir", None),
            )
            return 0

        # Set cookies env if provided
        if getattr(parsed, "cookies", None):
            os.environ["YOUTUBE_COOKIES_FILE"] = str(parsed.cookies)
        
        if parsed.analyze:
            sys.stdout.write(f"\n🔍 Executando Análise de Conteúdo Inteligente para: {parsed.input}...\n\n")
            from youtube_clipper.analyzer import extract_transcript_and_analyze
            analysis = extract_transcript_and_analyze(parsed.input)
            if not analysis["success"]:
                sys.stderr.write(f"Erro na análise: {analysis.get('error')}\n")
                return 1

            clips = analysis.get("clips", [])
            sys.stdout.write(f"✨ Foram encontrados {len(clips)} cortes sugeridos com alto engajamento:\n")
            sys.stdout.write("=" * 70 + "\n")

            for c in clips:
                sys.stdout.write(f"📌 Corte #{c['rank']} | Score: {c['score']}/100 | Título: {c['title']}\n")
                sys.stdout.write(f"   ⏱ Tempo: {c['start_timestamp']} -> {c['end_timestamp']} ({c['duration']}s)\n")
                sys.stdout.write(f"   📝 Resumo: {c['summary']}\n")
                sys.stdout.write(f"   🏷 Hashtags: {' '.join(c['hashtags'])}\n")
                sys.stdout.write(f"   💬 Transcrição: \"{c['transcript'][:120]}...\"\n")
                sys.stdout.write("-" * 70 + "\n")

            return 0

        # Delegate to pipeline module
        import youtube_clipper.pipeline as pipe_mod
        if hasattr(pipe_mod, "run_pipeline"):
            clip_path = pipe_mod.run_pipeline(
                input_source=parsed.input,
                start=parsed.start,
                end=parsed.end,
                duration=parsed.duration,
                output=parsed.output,
                fast=parsed.fast,
                verbose=parsed.verbose,
                vertical=getattr(parsed, "vertical", False)
            )

            # Upload to Google Drive if requested
            if getattr(parsed, "gdrive", False):
                sys.stdout.write(f"☁️ Enviando {clip_path} para o Google Drive...\n")
                from youtube_clipper.gdrive_uploader import upload_clip_to_gdrive
                upload_res = upload_clip_to_gdrive(clip_path, folder_id=getattr(parsed, "folder_id", None))
                if upload_res.get("success"):
                    sys.stdout.write(f"✅ Upload concluído no Google Drive!\n🔗 Link: {upload_res.get('web_view_link')}\n")
                else:
                    sys.stderr.write(f"⚠️ Aviso no upload: {upload_res.get('error')}\n")

            return 0

        return 0

    except ValidationError as exc:
        sys.stderr.write(f"Error: {exc.message}\n")
        return exc.exit_code
    except ClipperError as exc:
        sys.stderr.write(f"Error: {exc.message}\n")
        return exc.exit_code
    except Exception as exc:
        sys.stderr.write(f"Unexpected error: {exc}\n")
        return 1


cli_main = main

if __name__ == "__main__":
    sys.exit(main())
