# Project: YouTube AI Clipper — Solução Definitiva Google Drive & Web Dashboard Integration

## Architecture
- **CLI Module** (`src/youtube_clipper/cli.py`): Entrypoint parsing CLI flags (`--gdrive`, `--cookies`, `--folder-id`) and executing workflow pipelines.
- **GDrive Module** (`src/youtube_clipper/gdrive_uploader.py`): Multi-tier authentication resolution (OAuth2 Env Vars -> `token.json` -> Service Account) and direct uploads to user personal folders (`1mYLUnTMhdflzmYhee804Nj52jBQuOI8H`).
- **Analyzer Module** (`src/youtube_clipper/analyzer.py`): Subtitle extraction via `yt-dlp` using `--cookies` propagation, transcript parsing, viral hook scoring.
- **Web Dashboard Module** (`src/youtube_clipper/web_dashboard.py`): HTTP REST API endpoints (`/api/gdrive-upload`, `/api/generate-clip`, `/api/analyze`) and HTML/JS UI dashboard.
- **Test Suite** (`tests/`): Pytest suite with 397+ tests, mock fixtures in `tests/conftest.py`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | GDrive OAuth2 Env Auth | OAuth2 user credential loading from `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN` | M1 | survey |
| 2 | GDrive `token.json` Auth | OAuth2 user credential loading from `token.json` authorized user file | M1 | survey |
| 3 | GDrive Service Account Fallback | Transparent fallback to `service-account.json` when OAuth2 user credentials unavailable | M1 | survey |
| 4 | GDrive Target Folder ID | Default target folder `1mYLUnTMhdflzmYhee804Nj52jBQuOI8H` and custom `folder_id` upload support | M1 | survey |
| 5 | Quota Error 403 Resolution | Elimination of 403 `storageQuotaExceeded` via OAuth2 user account owner quota | M1 | survey |
| 6 | CLI `--folder-id` Flag | CLI parameter support for specifying target Google Drive folder ID | M2 | survey |
| 7 | CLI Subtitle `--cookies` Propagation | Passing `YOUTUBE_COOKIES_FILE` environment variable to `yt-dlp` in `analyzer.py` | M2 | survey |
| 8 | Web Dashboard `/api/gdrive-upload` `folder_id` | Parsing `folder_id` and `cookies` in POST `/api/gdrive-upload` and `/api/generate-clip` endpoints | M2 | survey |
| 9 | Web Dashboard UI Input | Adding GDrive folder ID input field and wiring in JS UI dashboard | M2 | survey |
| 10 | Comprehensive Unit & Integration Tests | Unit tests for OAuth2 env vars, `token.json`, fallback hierarchy, CLI flags, API endpoints | M3 | survey |
| 11 | Full Test Suite Execution & E2E Validation | Running and passing 100% of unit/integration tests (406+ tests) via `pytest` | M3 | survey |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Google Drive Auth & Upload Module | Refactor `gdrive_uploader.py` for OAuth2 auth resolution, fallback hierarchy, `1mYLUnTMhdflzmYhee804Nj52jBQuOI8H` default folder, and quota fix | none | DONE |
| M2 | CLI & Web Dashboard UI Integration | Update `cli.py`, `analyzer.py`, and `web_dashboard.py` for `--folder-id`, cookies propagation, REST API payload handling, and UI inputs | M1 | DONE |
| M3 | Test Suite Expansion & E2E Verification | Add unit tests for GDrive OAuth2, fallback precedence, CLI flags, API endpoints, and pass 100% of 406+ pytest tests | M1, M2 | IN_PROGRESS |

## Interface Contracts
### GDrive Uploader Contract
`upload_clip_to_gdrive(clip_path: str, folder_id: Optional[str] = None) -> Dict[str, Any]`
- Returns dict containing `web_view_link`, `file_id`, `name`, `status`.
- Default `folder_id` falls back to `DEFAULT_TARGET_FOLDER_ID = "1mYLUnTMhdflzmYhee804Nj52jBQuOI8H"`.

### CLI Contract
`youtube_clipper --gdrive --folder-id <FOLDER_ID> --cookies <COOKIES_FILE>`
- Parses `--folder-id` and passes to `upload_clip_to_gdrive`.
- Sets `os.environ["YOUTUBE_COOKIES_FILE"] = cookies_path`.

### Web Dashboard REST API Contract
`POST /api/gdrive-upload`
- Request JSON: `{"file_path": "...", "folder_id": "..."}`
- Response JSON: `{"status": "success", "gdrive_link": "...", "file_id": "..."}`

`POST /api/generate-clip`
- Request JSON: `{"url": "...", "start": "...", "end": "...", "gdrive": true, "folder_id": "...", "cookies": "..."}`

## Code Layout
- `src/youtube_clipper/gdrive_uploader.py`: Google Drive authentication and upload implementation.
- `src/youtube_clipper/cli.py`: CLI flags and argument handling.
- `src/youtube_clipper/analyzer.py`: Subtitle extraction and transcript analysis.
- `src/youtube_clipper/web_dashboard.py`: REST API server and HTML dashboard UI.
- `tests/test_gdrive_uploader.py`: Unit tests for Google Drive uploader.
- `tests/test_cli.py`: Unit tests for CLI.
- `tests/test_web_dashboard.py`: Unit tests for Web Dashboard API and UI.
