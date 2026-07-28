# YouTube AI Clipper & Analyzer Dashboard

A Python 3.x tool and glassmorphism web dashboard for automated YouTube and local video clipping, AI content analysis (viral hook scoring), 9:16 vertical video layout conversion (center crop & blurred background fill), and 1-click Google Drive upload.

## Features

- **CLI & Glassmorphism Web Dashboard**: Flexible command-line interface and interactive modern browser UI.
- **YouTube & Local Media Support**: Accepts YouTube URLs (via `yt-dlp`) or local `.mp4`, `.mkv`, `.avi` files.
- **AI Viral Hook Scoring**: Parses subtitles/transcripts to rank key moments by virality score, hook density, and engagement potential.
- **9:16 Vertical Video Converter**:
  - `crop_center`: Center crop 16:9 videos to 9:16 vertical format.
  - `blur_background`: Heavy blurred background fill with scaled, centered video foreground.
- **Google Drive Storage Integration**: Upload generated clips directly to Google Drive via Service Account credentials.
- **Automated Test Suite**: Full `pytest` coverage for validators, downloader, processor, video formatter, web API, and E2E pipelines.

## Prerequisites

- **Python**: 3.9 or higher
- **FFmpeg**: Required in system `PATH` for video processing and filter graph rendering.
- **yt-dlp**: Automated download manager for YouTube video streams and captions.

## Installation

1. Clone the repository and navigate to the project directory:
   ```bash
   cd youtube_clipper
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the package in editable mode with dependencies:
   ```bash
   pip install -e .
   ```
   Or install requirements directly:
   ```bash
   pip install -r requirements.txt
   ```

## CLI Usage

### 1. Basic Clip Extraction
Extract a clip from a YouTube video between timestamps 01:00 and 02:00:
```bash
python3 -m youtube_clipper "https://www.youtube.com/watch?v=3Vpf3EaE1mc" --start 00:01:00 --end 00:02:00 -o output_clip.mp4
```

### 2. Vertical 9:16 Shorts (Blurred Background Fill)
Convert a local horizontal video clip into a vertical 9:16 Short with blurred background:
```bash
python3 -m youtube_clipper local_video.mp4 --start 10 --duration 30 --vertical
```

### 3. AI Viral Hook Analysis
Analyze video transcript for top viral hook moments:
```bash
python3 -m youtube_clipper "https://www.youtube.com/watch?v=3Vpf3EaE1mc" --analyze
```

### 4. Upload Clip to Google Drive
Extract a clip and upload to Google Drive:
```bash
python3 -m youtube_clipper local_video.mp4 --start 0 --end 15 --gdrive
```

## Web Dashboard Usage

Start the web dashboard server from the CLI:
```bash
python3 -m youtube_clipper --dashboard
```
Or run the web module directly:
```bash
python3 -m youtube_clipper.web_dashboard --port 8080
```

Open your browser and navigate to `http://localhost:8080` to access the interactive dashboard.

The dashboard binds to `127.0.0.1` by default and stores generated/downloadable
clips in the dedicated `output/` directory. To expose it beyond the local
machine, an explicit bearer token is mandatory:

```bash
python3 -m youtube_clipper --dashboard --host 0.0.0.0 \
  --api-token 'replace-with-a-strong-token' --output-dir ./output
```

Remote clients must send `Authorization: Bearer <token>`. The upload endpoint
accepts only files inside the configured output directory.

### Gemini editor in every clip card

Configure Gemini on the server before starting the dashboard. The API key is
never sent to browser JavaScript:

```bash
export GEMINI_API_KEY='your-server-side-key'
# Optional; the default is gemini-3.6-flash
export GEMINI_MODEL='gemini-3.6-flash'
python3 -m youtube_clipper --dashboard
```

Open a suggested clip and select **Editar com Gemini**. The conversation can
propose a new time range, vertical framing, blur, editorial overlay, audio,
soundtrack volume, and opening-image duration. Model output is accepted only as
a validated settings patch: it cannot execute commands or start a render. Review
the resulting controls and explicitly confirm the configuration to generate a
new MP4.

Soundtracks (up to 25 MiB) and opening images (PNG, JPEG, or WebP, up to 8 MiB)
are uploaded as local, opaque asset IDs under the configured output directory.
The server requires a rights confirmation, verifies extension, media type,
signature, size, and SHA-256, caps persistent assets at 200 files or 512 MiB,
and never accepts an asset path from the browser.
Use only media you own, license, or are authorized to edit.

## Pytest Test Suite

Execute the test suite using `pytest`:
```bash
.venv/bin/pytest -v
```
To run specific unit or integration test modules:
```bash
.venv/bin/pytest tests/test_e2e_pipeline.py -v
```

## Audit Logs and Troubleshooting

Every CLI invocation, dashboard request, pipeline execution, external command,
and Google Drive upload writes an isolated audit run under `runs/<run_id>/`.
The canonical `events.jsonl` uses lifecycle schema 2.0 and records whether each
planned action started, succeeded, failed, retried, was cancelled, or was
skipped, together with its next action and structured error details.

Subprocess stdout/stderr are stored under `commands/` and referenced by hash
from the event stream. Completed runs receive `seal.json`; an absent seal or an
action that started without a terminal event indicates an interrupted run.

See [docs/OBSERVABILIDADE.md](docs/OBSERVABILIDADE.md) for the event contract
and investigation runbook. Runs are append-only and must never be edited or
deleted; repeat a failed operation with a new run ID.

## License

MIT License
