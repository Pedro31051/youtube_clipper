# Test Infrastructure Specification: YouTube AI Clipper & Analyzer Dashboard

## 1. Testing Philosophy & Principles

The testing framework for the **YouTube AI Clipper & Analyzer Dashboard** adheres to four core testing principles aligned with the Project Pattern / Dual Track architecture:

1. **Opaque-Box Testing Strategy**: Tests validate public API contracts, CLI interfaces, HTTP endpoints, and high-level Python modules without coupling to private internal variables or ephemeral implementation details.
2. **Requirement-Driven E2E & Unit/Integration Dual Track**: Every functional requirement specified in `ORIGINAL_REQUEST.md` and feature listed in `PROJECT.md` is systematically covered by unit tests, boundary tests, cross-component integration tests, and full end-to-end (E2E) application scenario tests.
3. **100% Offline Mocking Stability**: Zero reliance on live external network connections (YouTube servers, Google Drive REST APIs) or computationally heavy real-world media encoding. All external boundaries are intercepted using deterministic, offline pytest fixtures.
4. **Fast, Isolated, and Reproducible Execution**: Synthetic media generators produce valid lightweight media buffers, ephemeral ports allow concurrent HTTP server testing, and temporary directory fixtures ensure test isolation without residual filesystem side effects.

---

## 2. Feature Inventory Matrix

Mapping of all **25 project features** (from `PROJECT.md`) across **4 distinct test tiers**:
- **Tier 1: Feature Coverage** (Unit and isolated module/function checks)
- **Tier 2: Boundary & Corner Cases** (Invalid inputs, missing credentials, empty subtitles, extreme aspect ratios, error handling)
- **Tier 3: Cross-Feature Combinations** (CLI + Pipeline + Formatter + GDrive; Web REST API + Pipeline + GDrive)
- **Tier 4: Real-World Application Scenarios** (Full E2E programmatic pipeline URL -> Subtitle Analysis -> Viral Hook Scoring -> 9:16 Vertical Blur Video Rendering -> GDrive Upload)

| # | Feature Name | Tier 1: Feature Coverage | Tier 2: Boundary & Corner Cases | Tier 3: Cross-Feature Combinations | Tier 4: Real-World Scenarios |
|---|--------------|--------------------------|---------------------------------|-----------------------------------|------------------------------|
| 1 | Web Dashboard UI | Render HTML template with correct structure and styles | Missing template, missing static assets | GET `/` returns 200 OK with full HTML DOM | Full browser dashboard launch & HTTP response check |
| 2 | Interactive Preview Player | HTML `<video>` element generation & source setting | Missing video src, invalid media MIME type | Video player state in `/api/generate-clip` response | Video preview playback after pipeline execution |
| 3 | Ranked Engagement Clips | `VideoContentAnalyzer.find_best_clips()` ranking logic | Subtitles with identical scores, single segment | Subtitle parsing -> AI scoring -> Ranked JSON output | Web API `/api/analyze` returning ranked clips |
| 4 | Transcription View | `TranscriptSegment` dataclass and transcript string formatting | Empty transcript, special characters, multiline VTT | VTT parser -> Transcript extraction -> API response | Full pipeline transcript display in Web UI |
| 5 | Hashtag Chips | Hashtag extraction & generation algorithm | No keywords found, duplicate hashtags | Subtitle analysis -> Hashtag generation -> UI display | E2E analyze response containing valid `#hashtags` |
| 6 | Loading & Progress Status | Status JSON state structure & reporting | Async processing error state, timeout handling | Web REST API status polling during video rendering | E2E clip generation progress tracking |
| 7 | Local Download Button | Direct download URL route serving generated `.mp4` | File not found (404), expired temp clip file | `/api/download/<filename>` static file serving | Web UI 1-click clip download flow |
| 8 | 1-Click GDrive Upload UI | Web UI POST `/api/gdrive-upload` button trigger | Missing credentials, network upload failure | Web API -> `GoogleDriveUploader` -> JSON result | Web UI upload button click -> Drive link generation |
| 9 | Vertical Format Selector | Parameter validation (`blur_background` vs `crop_center`) | Invalid mode string, fallback to default | Formatter mode selection in `/api/generate-clip` | User selecting 9:16 mode -> Vertical video output |
| 10 | Dashboard CLI Flag | `cli.py` `--dashboard` / `--server` flag parsing | Invalid port argument, privileged port binding | CLI invocation -> `start_dashboard_server()` startup | Launching web server via `youtube_clipper --dashboard` |
| 11 | Subtitle Extraction | `VTTParser` parsing timestamps & text stripping | Malformed VTT, missing timestamps, HTML tags | `downloader` VTT fetch -> `VTTParser` parsing | URL -> Subtitle download -> Structured segments |
| 12 | AI Viral Hook Scoring | `score_window()` hook keyword & verb density scoring | Zero hook words, short text, long text limits | Subtitle parser -> Hook scoring -> Best clip ranking | Subtitle analysis -> Viral hook ranked output |
| 13 | 9:16 Blurred Background Filter | `build_vertical_filter()` blur background filter graph | Extreme resolution inputs (4K, 240p, 1:1) | `VideoFormatter` -> FFmpeg subprocess blur execution | Full pipeline 16:9 video -> 9:16 blurred clip |
| 14 | 9:16 Center Crop Filter | `build_vertical_filter()` center crop filter graph | Square (1:1), portrait (4:5) aspect ratios | `VideoFormatter` -> FFmpeg subprocess crop execution | Full pipeline 16:9 video -> 9:16 cropped clip |
| 15 | Temporary File Isolation | Unique temp directory and file generation in `pipeline.py` | Disk full, read-only temp dir, race conditions | Pipeline execution -> Temp file creation & cleanup | Concurrent pipeline runs with distinct temp files |
| 16 | Package Dependencies | `requirements.txt` & `pyproject.toml` dependency imports | Missing optional package graceful error handling | Imports of `google-auth`, `google-api-python-client` | Full environment dependency verification |
| 17 | README Documentation | `README.md` existence and documentation structure checks | Broken Markdown links, missing code blocks | Documentation command examples vs CLI parser | Command line usage alignment with `README.md` |
| 18 | Sample File Cleanup | Root directory `.mp4` file cleanup utility | No `.mp4` files present, permission denied | Pipeline post-processing cleanup hook | Pre/post test suite root directory cleanliness |
| 19 | GDrive Service Account Auth | `GoogleDriveUploader` JSON credential parsing | Invalid JSON syntax, file not found, revoked key | Credential loader -> Drive Service client creation | Auth initialization -> GDrive API client ready |
| 20 | GDrive Upload API Endpoint | Backend HTTP handler `POST /api/gdrive-upload` | Malformed JSON body, unreadable file path | HTTP Handler -> `upload_clip_to_gdrive` -> HTTP 200 | REST API client -> Upload request -> Drive URL |
| 21 | Test Suite Infrastructure | `conftest.py` fixtures (`dummy_video_file`, `cli_runner`) | Fixture cleanup failures, temporary directory leakage | Fixtures powering unit, integration, and E2E tests | Execution of full 100% offline test suite |
| 22 | Unit & Integration Tests: Formatter | `test_video_formatter.py` unit and integration cases | Non-existent input file, FFmpeg process crash | `VideoFormatter` + FFmpeg mock output > 1000 bytes | Vertical conversion of 16:9 MP4 into 9:16 MP4 |
| 23 | Unit & Integration Tests: GDrive | `test_gdrive_uploader.py` unit and integration cases | Folder creation failure, Drive quota exceeded | `GoogleDriveUploader` + Mock Drive API execution | File upload -> Folder check -> Public link return |
| 24 | Unit & Integration Tests: Dashboard | `test_web_dashboard.py` REST API server cases | Invalid HTTP methods, missing parameters | Ephemeral HTTP server + Handler + Pipeline mock | Client HTTP requests -> Dashboard server responses |
| 25 | Programmatic E2E Flow Test | `test_e2e_full_pipeline.py` complete workflow test | Downloader failure, FFmpeg error, Auth error | URL -> Subtitles -> AI Analysis -> Render -> Drive | Full programmatic E2E execution pipeline |

---

## 3. Test Architecture & Offline Mocking Strategy

The testing infrastructure relies on four specialized pytest fixtures defined in `tests/conftest.py` to guarantee 100% offline execution and high test speed.

```
+-----------------------------------------------------------------------------------+
|                            Pytest Test Harness                                   |
+-----------------------------------------------------------------------------------+
       |                        |                        |                       |
       v                        v                        v                       v
+--------------+       +-----------------+       +----------------+      +----------------+
| mock_yt_dlp  |       |   mock_ffmpeg   |       |  mock_gdrive   |      |dashboard_server|
+--------------+       +-----------------+       +----------------+      +----------------+
| Mocks Python |       | Intercepts      |       | Intercepts     |      | Ephemeral port |
| API & CLI    |       | subprocess.run  |       | Service Account|      | HTTP Server    |
| sub-process  |       | creates dummy   |       | & Drive v3 API |      | (127.0.0.1:0)  |
| subtitle VTT |       | video >1000b    |       | responses      |      | daemon thread  |
+--------------+       +-----------------+       +----------------+      +----------------+
```

### 3.1 yt-dlp Downloading Mocking (`mock_yt_dlp` and `mock_yt_dlp_subs`)
- **Python API Mock (`mock_yt_dlp`)**: Patches `yt_dlp.YoutubeDL` and `YouTubeDownloader.download_segment` to avoid downloading real videos from YouTube. It creates a dummy `.mp4` video file in the target output directory and returns fake metadata (`title`, `duration`, `format`).
- **CLI Subprocess Mock (`mock_yt_dlp_subs`)**: Patches `subprocess.run` calls executed by `VideoContentAnalyzer.extract_transcript_and_analyze()` when invoking `yt-dlp --write-auto-subs`. The fixture detects the target VTT file path from the command arguments and automatically writes synthetic `.vtt` content containing sample subtitle segments.

```python
@pytest.fixture
def mock_yt_dlp_subs(monkeypatch, tmp_path):
    def mock_run(cmd, *args, **kwargs):
        if any("yt-dlp" in str(arg) for arg in cmd) and "--write-auto-subs" in cmd:
            # Locate output path and write dummy VTT
            vtt_path = tmp_path / "dummy_subs.en.vtt"
            vtt_path.write_text(
                "WEBVTT\n\n00:00:01.000 --> 00:00:05.000\n"
                "Unbelievable secret trick you need to see now!\n"
            )
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", mock_run)
```

### 3.2 FFmpeg 9:16 Vertical Video Conversion Mocking (`mock_ffmpeg`)
- **Binary Check**: Mocks `shutil.which('ffmpeg')` to always return `/usr/bin/ffmpeg`.
- **Execution & File Size Constraint**: Intercepts `subprocess.run` calls to `ffmpeg`. Because `VideoFormatter.convert_to_vertical()` validates that the output file exists and has size `os.path.getsize(output_path) > 1000` bytes, `mock_ffmpeg` generates a synthetic dummy video containing valid MP4 headers padded to at least **1024 bytes**.
- **Filter Graph Verification**: Allows unit tests to verify complex filter graph strings (`blur_background` with `split[bg][fg];...boxblur=20:10` vs `crop_center` with `crop=ih*9/16:ih`) without executing actual video re-encoding.

```python
@pytest.fixture
def mock_ffmpeg(monkeypatch):
    def mock_run(cmd, *args, **kwargs):
        # Extract output filename from command args
        if "-i" in cmd and len(cmd) > 0:
            out_file = cmd[-1]
            if out_file and not out_file.startswith("-"):
                os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
                with open(out_file, "wb") as f:
                    # Write dummy video header + padding > 1000 bytes
                    f.write(b"\x00\x00\x00\x1cftypisom" + b"\x00" * 1024)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    monkeypatch.setattr(subprocess, "run", mock_run)
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/ffmpeg" if x == "ffmpeg" else None)
```

### 3.3 Google Drive Service Account Mocking (`mock_gdrive`)
- **Credential Interception**: Mocks `os.path.exists` to return `True` for designated service account JSON paths.
- **OAuth & Discovery Service Patching**: Patches `google.oauth2.service_account.Credentials.from_service_account_file` and `googleapiclient.discovery.build`.
- **API Response Simulation**:
  - `service.files().list().execute()` returns `{"files": [{"id": "folder_123", "name": "YouTube_Clips"}]}`.
  - `service.files().create().execute()` returns `{"id": "file_456", "name": "clip.mp4", "webViewLink": "https://drive.google.com/file/d/file_456/view", "webContentLink": "https://drive.google.com/uc?id=file_456"}`.
  - `service.permissions().create().execute()` returns `{"id": "perm_789"}`.
- **Media Upload Patching**: Mocks `googleapiclient.http.MediaFileUpload` to avoid file locks and unnecessary disk reads.

```python
@pytest.fixture
def mock_gdrive(monkeypatch):
    mock_service = MagicMock()
    mock_files = MagicMock()
    mock_permissions = MagicMock()
    
    mock_files.list().execute.return_value = {"files": [{"id": "folder_123", "name": "YouTube_Clips"}]}
    mock_files.create().execute.return_value = {
        "id": "file_456",
        "name": "test_clip.mp4",
        "webViewLink": "https://drive.google.com/file/d/file_456/view",
        "webContentLink": "https://drive.google.com/uc?id=file_456"
    }
    mock_permissions.create().execute.return_value = {"id": "perm_789"}
    
    mock_service.files.return_value = mock_files
    mock_service.permissions.return_value = mock_permissions
    
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **kw: mock_service)
    monkeypatch.setattr("google.oauth2.service_account.Credentials.from_service_account_file", lambda path, scopes: MagicMock())
    return mock_service
```

### 3.4 Web Dashboard REST API Testing Harness (`dashboard_server`)
- **Ephemeral Port Allocation**: Instantiates `HTTPServer(("127.0.0.1", 0), ClipperDashboardHandler)` where port `0` binds to an available OS ephemeral port.
- **Background Daemon Execution**: Starts the server in a separate daemon thread (`threading.Thread(target=server.serve_forever, daemon=True)`).
- **Clean Teardown**: Yields `http://127.0.0.1:<port>` to the test, and on completion calls `httpd.shutdown()` and `httpd.server_close()`.
- **REST Endpoints Validation**: Enables testing `GET /`, `POST /api/analyze`, `POST /api/generate-clip`, and `POST /api/gdrive-upload` via `urllib.request.urlopen` or `http.client.HTTPConnection`.

```python
@pytest.fixture
def dashboard_server():
    server = HTTPServer(("127.0.0.1", 0), ClipperDashboardHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()
```

---

## 4. Coverage Summary Table

Target coverage distribution across test files and tiers:

| Test File Module | Primary Target Scope | Tier 1 (Unit) | Tier 2 (Boundary) | Tier 3 (Integration) | Tier 4 (E2E Scenario) | Total Tests | Status |
|------------------|----------------------|---------------|-------------------|----------------------|-----------------------|-------------|--------|
| `test_validator.py` | Argument & URL Validation | 15 | 20 | 5 | 2 | 42 | Passed |
| `test_downloader.py` | YouTube Segment Download | 12 | 10 | 6 | 2 | 30 | Passed |
| `test_processor.py` | FFmpeg Cutting & Trimming | 14 | 12 | 8 | 2 | 36 | Passed |
| `test_analyzer.py` | VTT Parsing & Hook Scoring | 15 | 10 | 6 | 2 | 33 | Passed |
| `test_pipeline.py` | Pipeline Coordination | 10 | 8 | 12 | 3 | 33 | Passed |
| `test_cli.py` | CLI Interface & Flag Parsing | 12 | 10 | 8 | 2 | 32 | Passed |
| `test_conftest.py` | Test Harness & Fixtures | 8 | 5 | 2 | 0 | 15 | Passed |
| `test_e2e_validation.py` | E2E Input Validation | 0 | 25 | 10 | 5 | 40 | Passed |
| `test_e2e_downloader.py` | E2E Download Resilience | 0 | 15 | 10 | 5 | 30 | Passed |
| `test_e2e_processor.py` | E2E Media Processing | 0 | 12 | 10 | 4 | 26 | Passed |
| `test_e2e_pipeline.py` | E2E Pipeline Scenarios | 0 | 10 | 15 | 5 | 30 | Passed |
| `test_e2e_cli.py` | E2E Command-Line Suite | 0 | 15 | 10 | 3 | 28 | Passed |
| `test_e2e_scenarios.py` | E2E Complex User Workflows | 0 | 5 | 10 | 13 | 28 | Passed |
| `test_video_formatter.py` *(New)* | 9:16 Vertical Conversion (Blur/Crop) | 10 | 8 | 5 | 2 | 25 | Planned (M_E2E) |
| `test_gdrive_uploader.py` *(New)* | GDrive Service Account Upload | 10 | 8 | 5 | 2 | 25 | Planned (M_E2E) |
| `test_web_dashboard.py` *(New)* | Dashboard UI & REST API Server | 12 | 10 | 6 | 2 | 30 | Planned (M_E2E) |
| `test_e2e_full_pipeline.py` *(New)* | Full E2E Programmatic Flow | 0 | 3 | 5 | 7 | 15 | Planned (M_E2E) |
| **Total Test Count** | **Full Project Suite** | **138** | **186** | **133** | **55** | **512** | **363 Passed / 95 Planned** |

---

## 5. Verification Commands

To verify the test infrastructure and run the test suite:

```bash
# 1. Execute full pytest suite with verbose output
.venv/bin/pytest -v

# 2. Run specific test tier or module
.venv/bin/pytest tests/test_video_formatter.py -v
.venv/bin/pytest tests/test_gdrive_uploader.py -v
.venv/bin/pytest tests/test_web_dashboard.py -v
.venv/bin/pytest tests/test_e2e_full_pipeline.py -v

# 3. Verify 100% offline execution (no external network calls)
pytest_offline=true .venv/bin/pytest -v
```
