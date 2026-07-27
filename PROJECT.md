# Project: youtube_clipper Phase T2 (Technical Short Pipeline)

## Architecture
Phase T2 delivers an end-to-end 9-stage technical short pipeline generating 9:16 vertical videos (1080x1920) from local video files, backed by atomic audit logging (`cortes.log`), zero-trust read-only physical verification (`cortes.verify`), gapless AST security contracts (`test_contracts.py`), and a complete review package (`review/T2/`).

Module Boundaries & Data Flow:
`ingest` -> `transcribe` -> `scenes` -> `select` -> `cut` -> `subtitles` -> `audio` -> `render` -> `report` -> `verify`

Shared Interfaces:
- Audit contract: `@audited(stage=...)` decorator on all stage functions.
- Command execution: `cortes.log.run_cmd()` subprocess gateway (logs to `commands.log` and `events.jsonl`).
- Verification engine: `cortes.verify.verify_run(run_dir, audit=False)` read-only verification producing `verify_result.json`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Dependencies Setup | Install `faster-whisper`, `scenedetect`, `pysubs2`, `pyloudnorm`, `soundfile` in `.venv` | M1 | survey |
| 2 | AST Scanner & Audit Contract | Enforce zero direct subprocess calls and `@audited` decorator across `src/` and `tests/` | M1 | survey |
| 3 | Pipeline Ingest Stage | Local video ingestion & metadata validation (`run_ingest`) | M2 | survey |
| 4 | Pipeline Transcribe Stage | Whisper GPU transcription with word-level timestamps (`run_transcribe`) | M2 | survey |
| 5 | Pipeline Scenes Stage | PySceneDetect scene boundary detection (`run_scenes`) | M2 | survey |
| 6 | Pipeline Select Stage | Deterministic heuristic selection (max speech density window 20s-58s aligned to scene cut) (`run_select`) | M2 | survey |
| 7 | Pipeline Cut Stage | FFmpeg fast cut (`-c copy`) of clip segment (`run_cut`) | M3 | survey |
| 8 | Pipeline Subtitles Stage | Word-level ASS subtitles generation via `pysubs2` (`run_subtitles`) | M3 | survey |
| 9 | Pipeline Audio Stage | Two-pass FFmpeg `loudnorm` audio processing (-16 to -13 LUFS) (`run_audio`) | M3 | survey |
| 10 | Pipeline Render Stage | 9:16 vertical render (1080x1920) with burned ASS subtitles via libass (`run_render`) | M3 | survey |
| 11 | Pipeline Report Stage | Generation of `report.md` from `events.jsonl` and `verify_result.json` (`run_report`) | M3 | survey |
| 12 | Zero-Trust Verification Engine | Read-only physical re-measurement in `verify.py` (constant FPS, selection bounds, subtitle alignment, LUFS, SHA-256) | M4 | survey |
| 13 | Golden Run Execution | Execute end-to-end T2 pipeline golden run producing `runs/run_t2_golden/` | M4 | survey |
| 14 | Review Package & Git Branch | Consolidate `review/T2/` manifest and push branch `agent/t2-short-tecnico` to GitHub | M5 | survey |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Infrastructure & Audit Contracts | Dependencies installation, AST security contract enforcement (`test_contracts.py`) | None | DONE |
| M2 | Pipeline Core Stages (1-4) | Stage 1 (ingest), Stage 2 (transcribe Whisper GPU), Stage 3 (scenes PySceneDetect), Stage 4 (select speech density heuristic) | M1 | DONE |
| M3 | Pipeline Output Stages (5-9) | Stage 5 (cut), Stage 6 (subtitles .ass), Stage 7 (audio 2-pass loudnorm), Stage 8 (render 9:16 vertical), Stage 9 (report) | M2 | PLANNED |
| M4 | Zero-Trust Verification & Golden Run | Incremental `verify.py` checks, execute golden run `runs/run_t2_golden/` and verify pass | M3 | PLANNED |
| M5 | Review Package & Git Branch Delivery | Consolidate `review/T2/` review package and push branch `agent/t2-short-tecnico` | M4 | PLANNED |

## Interface Contracts
### `src/cortes/log.py` ↔ Stage Modules (`src/cortes/*.py`)
- Every stage function MUST be decorated with `@audited(stage="<stage_name>")`.
- Every external command invocation MUST pass through `cortes.log.run_cmd(cmd, cwd, audit=True|False)`.

### Stage Modules ↔ `src/cortes/verify.py`
- `verify.py` executes `verify_run(run_dir, audit=False)` without mutating files or logs.
- `verify.py` outputs `verify_result.json` strictly outside `run_dir`.

### Pipeline Output ↔ Review Package (`review/T2/`)
- `runs/run_t2_golden/` contains `events.jsonl`, `commands.log`, `short.mp4`, `report.md`.
- `review/T2/` contains `PACOTE.md`, `runs/run_t2_golden/`, `diff.patch`, `files_changed.txt`, `verify_result.json`, `report.md`, `DECISOES.md`, `LIMITACOES.md`, `CRITICA_INTERNA.md`.

## Code Layout
- `src/cortes/`: Audit logger (`log.py`), verifier (`verify.py`), report generator (`report.py`), stage wrapper modules (`ingest.py`, `transcribe.py`, `scenes.py`, `select.py`, `cut.py`, `subtitles.py`, `audio.py`, `transform.py`, `render.py`).
- `src/youtube_clipper/`: Domain logic modules (`cli.py`, `pipeline.py`, `processor.py`, `analyzer.py`, `video_formatter.py`, etc.).
- `tests/`: Contract tests (`test_contracts.py`), mutation tests (`test_mutation.py`), e2e tests (`test_e2e_*.py`).
- `review/T2/`: Review package delivery artifacts.
