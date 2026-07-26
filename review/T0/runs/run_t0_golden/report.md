# Execution & Verification Report — Run `run_t0_golden`

**Generated At**: `2026-07-26T22:54:30.705909+00:00`  
**Verification Verdict**: `PASSED`

---

## 1. Run Metadata Summary

| Attribute | Value |
|---|---|
| **Run ID** | `run_t0_golden` |
| **Video ID** | `test_video_t0` |
| **Clip ID** | `null` |
| **Agent** | `worker` |
| **Start Time (UTC)** | `2026-07-26T22:30:00.000000Z` |
| **End Time (UTC)** | `2026-07-26T22:54:30.967535+00:00` |
| **Total Events** | `8` |
| **Total Duration (ms)** | `5767.28` |

---

## 2. Stage Execution Log (`events.jsonl`)

| Seq | Stage | Attempt | Tool / Command | Exit Code | Outcome | Duration (ms) |
|---|---|---|---|---|---|---|
| 1 | env | 1 | `python` | 0 | ok | 12.5 |
| 2 | ingest | 1 | `python` | 0 | ok | 450.0 |
| 3 | transcribe | 1 | `python` | 0 | ok | 820.0 |
| 4 | cut | 1 | `python` | 0 | ok | 310.0 |
| 5 | subtitles | 1 | `python` | 0 | ok | 190.0 |
| 6 | render | 1 | `ffmpeg -y -f lavfi -i testsrc=size=1080x1920:rate=15 -f l...` | 0 | ok | 1500.0 |
| 7 | verify | 1 | `ffprobe -v error -show_format -show_streams -of json /hom...` | 0 | ok | 218.54 |
| 8 | verify | 1 | `ffmpeg -nostdin -nostats -hide_banner -i /home/pedrofelip...` | 0 | ok | 2266.24 |

---

## 3. Verification Check Results (`verify_result.json`)

| Check ID | Status | Measured | Expected | Evidence Path |
|---|---|---|---|---|
| `events_file_exists` | PASS | File exists | File exists | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `events_schema_valid` | PASS | Validated 6 events | Schema Version 1.0.0 valid | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `seq_integrity` | PASS | seq 1..N continuous without gaps and stage DAG sequence valid | seq == index + 1 without gaps or duplicates and stage DAG sequence valid | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `ts_monotonic` | PASS | Timestamps non-decreasing | Monotonic non-decreasing ISO timestamps | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `commands_log_sync` | PASS | Commands log in sync | All event commands present in commands.log | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/commands.log` |
| `exit_codes_zero` | PASS | All ok events have exit_code 0 | exit_code == 0 for all outcome ok events | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `producer_evidence_required` | PASS | All producer ok events have evidence paths | Producer stages with outcome ok must declare non-empty evidence paths | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `artifact_exists` | PASS | All declared evidence artifacts exist | All evidence files exist on disk | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `artifact_sha256` | PASS | All SHA-256 hashes match | Calculated SHA-256 matches declared hash | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `artifact_bytes` | PASS | All byte sizes match | Disk byte size matches declared size | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/events.jsonl` |
| `video_resolution` | PASS | 1080x1920 | 1080x1920 | `run_t0_golden/artifacts/render/short.mp4` |
| `audio_stream_count` | PASS | 1 audio stream(s) | Exactly 1 audio stream | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/render/short.mp4` |
| `video_duration_range` | PASS | 25.0 seconds | 20.0 <= duration <= 58.0 seconds | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/render/short.mp4` |
| `audio_lufs_loudness` | PASS | -14.50 LUFS | [-16.0 LUFS, -13.0 LUFS] | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/render/short.mp4` |

---

## 4. Produced Artifacts & Cryptographic Signatures

| Stage | Path | Bytes | SHA-256 Hash |
|---|---|---|---|
| ingest | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/source_metadata.json` | 69 | `sha256:64843e0582af8f24f157bf734145bcd4a91996bce321a78d70fc55b581e69941` |
| transcribe | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/transcript.json` | 113 | `sha256:4076c13c0f0dd87d686d34085c0239b1360c3fd1e49d670516b72528c905bffe` |
| cut | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/cut_info.json` | 60 | `sha256:7053369e5032843cd8d194f84426405713c50584bdb5cd0a41bf184622cccf42` |
| subtitles | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/subtitles.ass` | 38 | `sha256:82bfb89f5930876de3e47fb768de1606b8d5d3ecc763de1a5a199f5bf8c38b2a` |
| render | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/render/short.mp4` | 1783078 | `sha256:c8c886a6a541d92d72951272385b53498b892ee5371b7722087b9e8f1d7f1a43` |

---

## 5. Executed Subprocess Commands (`commands.log`)

```bash
ffmpeg -y -f lavfi -i testsrc=size=1080x1920:rate=15 -f lavfi -i sine=frequency=440:sample_rate=48000 -af loudnorm=I=-14.5:TP=-1.5:LRA=11 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -t 25 -shortest /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/render/short.mp4
ffprobe -v error -show_format -show_streams -of json /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/render/short.mp4
ffmpeg -nostdin -nostats -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t0_golden/artifacts/render/short.mp4 -filter_complex ebur128=peak=true -f null -
```

---

## 6. Final Integrity Verdict

- **Overall Status**: `PASSED`
- **Total Checks Passed**: `14/14`
