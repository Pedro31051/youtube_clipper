# Execution & Verification Report — Run `run_t1_golden`

**Generated At**: `2026-07-27T12:10:51.281176+00:00`  
**Verification Verdict**: `PASSED`

---

## 1. Run Metadata Summary

| Attribute | Value |
|---|---|
| **Run ID** | `run_t1_golden` |
| **Video ID** | `test_video_t1` |
| **Clip ID** | `null` |
| **Agent** | `worker_t1` |
| **Start Time (UTC)** | `2026-07-27T12:10:43.523093+00:00` |
| **End Time (UTC)** | `2026-07-27T12:10:43.538599+00:00` |
| **Total Events** | `6` |
| **Total Duration (ms)** | `4057.87` |

---

## 2. Stage Execution Log (`events.jsonl`)

| Seq | Stage | Attempt | Tool / Command | Exit Code | Outcome | Duration (ms) |
|---|---|---|---|---|---|---|
| 1 | env | 1 | `python` | 0 | ok | 0.0 |
| 2 | ingest | 1 | `python` | 0 | ok | 0.0 |
| 3 | transcribe | 1 | `python` | 0 | ok | 0.0 |
| 4 | cut | 1 | `python` | 0 | ok | 0.0 |
| 5 | subtitles | 1 | `python` | 0 | ok | 0.0 |
| 6 | render | 1 | `ffmpeg -y -f lavfi -i testsrc=size=1080x1920:rate=15 -f l...` | 0 | ok | 4057.87 |

---

## 3. Verification Check Results (`verify_result.json`)

| Check ID | Status | Measured | Expected | Evidence Path |
|---|---|---|---|---|
| `events_file_exists` | PASS | File exists | File exists | `events.jsonl` |
| `events_schema_valid` | PASS | Validated 6 events | Schema Version 1.0.0 valid | `events.jsonl` |
| `seq_integrity` | PASS | seq 1..N continuous without gaps and stage DAG sequence valid | seq == index + 1 without gaps or duplicates and stage DAG sequence valid | `events.jsonl` |
| `ts_monotonic` | PASS | Timestamps non-decreasing | Monotonic non-decreasing ISO timestamps | `events.jsonl` |
| `commands_log_sync` | PASS | Commands log in sync | All event commands present in commands.log | `commands.log` |
| `exit_codes_zero` | PASS | All ok events have exit_code 0 | exit_code == 0 for all outcome ok events | `events.jsonl` |
| `producer_evidence_required` | PASS | All producer ok events have evidence paths | Producer stages with outcome ok must declare non-empty evidence paths | `events.jsonl` |
| `artifact_exists` | PASS | All declared evidence artifacts exist | All evidence files exist on disk | `events.jsonl` |
| `artifact_sha256` | PASS | All SHA-256 hashes match | Calculated SHA-256 matches declared hash | `events.jsonl` |
| `artifact_bytes` | PASS | All byte sizes match | Disk byte size matches declared size | `events.jsonl` |
| `video_resolution::artifacts/render/short.mp4` | PASS | 1080x1920 | 1080x1920 | `artifacts/render/short.mp4` |
| `audio_stream_count::artifacts/render/short.mp4` | PASS | 1 audio stream(s) | Exactly 1 audio stream | `artifacts/render/short.mp4` |
| `video_duration_range::artifacts/render/short.mp4` | PASS | 25.0 seconds | 20.0 <= duration <= 58.0 seconds | `artifacts/render/short.mp4` |
| `audio_lufs_loudness::artifacts/render/short.mp4` | PASS | -14.50 LUFS | [-16.0 LUFS, -13.0 LUFS] | `artifacts/render/short.mp4` |

---

## 4. Produced Artifacts & Cryptographic Signatures

| Stage | Path | Bytes | SHA-256 Hash |
|---|---|---|---|
| ingest | `artifacts/source_metadata.json` | 77 | `sha256:85036d1bf8fb11233376aa4b300e0e5ac3543830d20ba8e5ee173ecf435d5310` |
| transcribe | `artifacts/transcript.json` | 57 | `sha256:6c18964953beca722b2db120f68d9805839c3fb6c17e3bc6b0e1d0533fde53b6` |
| cut | `artifacts/cut_info.json` | 80 | `sha256:eb03d5878fc6d46de39b26ce2ff5166ef802da5c883f69349986de8605e9e301` |
| subtitles | `artifacts/subtitles.ass` | 34 | `sha256:a5889631ef939fd88b02af97338bb9c2fe47c9c7164e8bd5e10ca88fb8a604b8` |
| render | `artifacts/render/short.mp4` | 1783078 | `sha256:c8c886a6a541d92d72951272385b53498b892ee5371b7722087b9e8f1d7f1a43` |

---

## 5. Executed Subprocess Commands (`commands.log`)

```bash
ffmpeg -y -f lavfi -i testsrc=size=1080x1920:rate=15 -f lavfi -i sine=frequency=440:sample_rate=48000 -af loudnorm=I=-14.5:TP=-1.5:LRA=11 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -t 25 -shortest runs/run_t1_golden/artifacts/render/short.mp4
```

---

## 6. Final Integrity Verdict

- **Overall Status**: `PASSED`
- **Total Checks Passed**: `14/14`
