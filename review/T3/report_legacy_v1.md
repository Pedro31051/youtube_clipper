# Execution & Verification Report — Run `run_t3_golden`

**Generated At**: `2026-07-27T17:42:24.154073+00:00`  
**Verification Verdict**: `PASSED`

---

## 1. Run Metadata Summary

| Attribute | Value |
|---|---|
| **Run ID** | `run_t3_golden` |
| **Video ID** | `unknown` |
| **Clip ID** | `null` |
| **Agent** | `worker` |
| **Start Time (UTC)** | `2026-07-27T17:41:04.967733+00:00` |
| **End Time (UTC)** | `2026-07-27T17:42:13.348118+00:00` |
| **Total Events** | `36` |
| **Total Duration (ms)** | `185052.73` |

---

## 2. Stage Execution Log (`events.jsonl`)

| Seq | Stage | Attempt | Tool / Command | Exit Code | Outcome | Duration (ms) |
|---|---|---|---|---|---|---|
| 1 | env | 1 | `ffmpeg -y -f lavfi -i testsrc=duration=30:size=640x360:ra...` | 0 | ok | 12761.39 |
| 2 | env | 1 | `python` | 0 | ok | 12775.36 |
| 3 | ingest | 1 | `ffprobe -v error -show_format -show_streams -of json /hom...` | 0 | ok | 303.59 |
| 4 | ingest | 1 | `python` | 0 | ok | 355.9 |
| 5 | ingest | 1 | `python` | 0 | ok | 365.69 |
| 6 | transcribe | 1 | `ffmpeg -y -nostdin -v error -i /home/pedrofelipealvesroch...` | 0 | ok | 567.34 |
| 7 | transcribe | 1 | `python` | 0 | ok | 577.98 |
| 8 | transcribe | 1 | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_cli...` | 0 | ok | 9972.57 |
| 9 | transcribe | 1 | `python` | 0 | ok | 9987.21 |
| 10 | transcribe | 1 | `python` | 0 | ok | 10582.84 |
| 11 | scenes | 1 | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_cli...` | 0 | ok | 5097.28 |
| 12 | scenes | 1 | `ffprobe -v error -show_entries format=duration -of json /...` | 0 | ok | 104.56 |
| 13 | scenes | 1 | `python` | 0 | ok | 5216.15 |
| 14 | select | 1 | `python` | 0 | ok | 6.73 |
| 15 | cut | 1 | `ffprobe -v error -show_entries format=duration -of defaul...` | 0 | ok | 99.22 |
| 16 | cut | 1 | `ffmpeg -y -ss 0.0 -i /home/pedrofelipealvesrocha/teamwork...` | 0 | ok | 149.95 |
| 17 | cut | 1 | `ffprobe -v error -show_entries format=duration -of defaul...` | 0 | ok | 134.92 |
| 18 | cut | 1 | `python` | 0 | ok | 403.23 |
| 19 | cut | 1 | `python` | 0 | ok | 408.97 |
| 20 | subtitles | 1 | `python` | 0 | ok | 0.04 |
| 21 | subtitles | 1 | `python` | 0 | ok | 0.06 |
| 22 | subtitles | 1 | `python` | 0 | ok | 0.04 |
| 23 | subtitles | 1 | `python` | 0 | ok | 0.06 |
| 24 | subtitles | 1 | `python` | 0 | ok | 15.04 |
| 25 | subtitles | 1 | `python` | 0 | ok | 19.09 |
| 26 | audio | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 2327.71 |
| 27 | audio | 1 | `python` | 0 | ok | 0.44 |
| 28 | audio | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 6258.9 |
| 29 | audio | 1 | `python` | 0 | ok | 8606.98 |
| 30 | audio | 1 | `python` | 0 | ok | 8621.75 |
| 31 | render | 1 | `python` | 0 | ok | 0.22 |
| 32 | render | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 28905.6 |
| 33 | render | 1 | `python` | 0 | ok | 30177.2 |
| 34 | render | 1 | `python` | 0 | ok | 30236.24 |
| 35 | report | 1 | `python` | 0 | ok | 1.98 |
| 36 | report | 1 | `python` | 0 | ok | 10.5 |

---

## 3. Verification Check Results (`verify_result.json`)

| Check ID | Status | Measured | Expected | Evidence Path |
|---|---|---|---|---|
| `events_file_exists` | PASS | File exists | File exists | `events.jsonl` |
| `events_schema_valid` | PASS | Validated 36 events | Schema Version 1.0.0 valid | `events.jsonl` |
| `seq_integrity` | PASS | seq 1..N continuous without gaps and stage DAG sequence valid | seq == index + 1 without gaps or duplicates and stage DAG sequence valid | `events.jsonl` |
| `ts_monotonic` | PASS | Timestamps non-decreasing | Monotonic non-decreasing ISO timestamps | `events.jsonl` |
| `commands_log_sync` | PASS | Commands log in sync | All event commands present in commands.log | `commands.log` |
| `exit_codes_zero` | PASS | All ok events have exit_code 0 | exit_code == 0 for all outcome ok events | `events.jsonl` |
| `evidence_paths_relative` | PASS | All evidence paths are run-relative | Every evidence path is relative and confined to the run | `events.jsonl` |
| `producer_evidence_required` | PASS | Every executed producer stage has at least one completion event with evidence | Producer stages with outcome ok must declare non-empty evidence paths | `events.jsonl` |
| `artifact_exists` | PASS | All declared evidence artifacts exist | All evidence files exist on disk | `events.jsonl` |
| `artifact_sha256` | PASS | All SHA-256 hashes match | Calculated SHA-256 matches declared hash | `events.jsonl` |
| `artifact_bytes` | PASS | All byte sizes match | Disk byte size matches declared size | `events.jsonl` |
| `intermediate_media_valid::artifacts/audio/audio_normalized.mp4` | PASS | size=841497 bytes, duration=26.4s | size > 1024 bytes and duration > 0.0s | `artifacts/audio/audio_normalized.mp4` |
| `intermediate_media_valid::artifacts/cut/clip.mp4` | PASS | size=312378 bytes, duration=26.37s | size > 1024 bytes and duration > 0.0s | `artifacts/cut/clip.mp4` |
| `intermediate_media_valid::artifacts/ingest/source.mp4` | PASS | size=335176 bytes, duration=30.0s | size > 1024 bytes and duration > 0.0s | `artifacts/ingest/source.mp4` |
| `final_render_required` | PASS | 1 final render(s) found | At least one declared short.mp4 for a T2 run | `artifacts` |
| `video_resolution::artifacts/clip_bf969de3835e/short.mp4` | PASS | 1080x1920 | 1080x1920 | `artifacts/clip_bf969de3835e/short.mp4` |
| `video_constant_fps::artifacts/clip_bf969de3835e/short.mp4` | PASS | r_frame_rate=30.000000, avg_frame_rate=30.000000 | Positive constant FPS (r_frame_rate == avg_frame_rate) | `artifacts/clip_bf969de3835e/short.mp4` |
| `audio_stream_count::artifacts/clip_bf969de3835e/short.mp4` | PASS | 1 audio stream(s) | Exactly 1 audio stream | `artifacts/clip_bf969de3835e/short.mp4` |
| `video_duration_range::artifacts/clip_bf969de3835e/short.mp4` | PASS | 26.4 seconds | 20.0 <= duration <= 58.0 seconds | `artifacts/clip_bf969de3835e/short.mp4` |
| `audio_lufs_loudness::artifacts/clip_bf969de3835e/short.mp4` | PASS | -15.40 LUFS | [-16.0 LUFS, -13.0 LUFS] | `artifacts/clip_bf969de3835e/short.mp4` |
| `selection_within_source_bounds` | PASS | start_ms=0, end_ms=26120, source_duration_ms=30000 | 0 <= start_ms < end_ms <= source_duration_ms | `artifacts/select/selection.json` |
| `subtitle_word_alignment` | PASS | All ASS events map to transcript words within +/-200 ms | Non-empty ASS; every event maps to a transcript word within +/-200 ms and remains inside the selected interval | `artifacts/subtitles/subtitles.ass` |

---

## 4. Produced Artifacts & Cryptographic Signatures

| Stage | Path | Bytes | SHA-256 Hash |
|---|---|---|---|
| env | `scratch/LICENSE_PROOF.md` | 91 | `sha256:c9ba55def8537213ff74641651d6c7c40ee0113e09b4c95433249d8c1fa21a38` |
| ingest | `artifacts/ingest/source.mp4` | 335176 | `sha256:243f1d82766636fd1e24c69aa6fc81ff42b4bfd0923878692c5c828d5db1bd5f` |
| ingest | `artifacts/ingest/metadata.json` | 424 | `sha256:c453dfb0346e64ea1648f8cd00fa8acac515e9d3cfc9b034026d9525ac68bc97` |
| transcribe | `artifacts/transcribe/audio_16k.wav` | 962638 | `sha256:2a01b2aa1fa0460efad600dcba4de506b4a5c14a016bfeb14d3fb6d4a97a6c2e` |
| transcribe | `artifacts/transcribe/transcript.json` | 20145 | `sha256:f1343ab4088bd82601bd867593b8ee6916d4befd299d55f0b2d41c1835242c29` |
| scenes | `artifacts/scenes/scenes.json` | 1095 | `sha256:342b17f10a19e1f699eb02e4c485ca86c3db741e36f21c445f2430361098646c` |
| select | `artifacts/select/selection.json` | 182 | `sha256:bf969de3835e84cf3dfd0276b61f4080ee4f00b7d6b52584d0a9d9e6a4435594` |
| cut | `artifacts/cut/clip.mp4` | 312378 | `sha256:fbfbdd3f0a0550fc032b57b41866c2c66edd54417f3de33b28dda04712d9d9b4` |
| cut | `artifacts/cut/cut_metadata.json` | 157 | `sha256:cdd865e05fc8cf3b4848784da3dc2dadedc821b9662e5fa1fc94e34e004a1043` |
| subtitles | `artifacts/subtitles/subtitles.ass` | 3793 | `sha256:6e8cc6e717b55a741eab52167670810ed3afe2514f142783d223eba26fe8b7e2` |
| subtitles | `artifacts/subtitles/subtitle_mapping.json` | 13123 | `sha256:99e94c9340655bb742c48f9aa33a594a957863f0c557b22eae5ec270bd5d74d4` |
| audio | `artifacts/audio/audio_normalized.mp4` | 841497 | `sha256:b5dff7b74b28f858bc2365acbb41ddf39895bf73ad277927df71be129a605f52` |
| audio | `artifacts/audio/audio_stats.json` | 405 | `sha256:82bb3ad1a9e87c2dcfbc13aa8dcaf5040dcc2f6509758fd213518c5b817b02a8` |
| render | `artifacts/clip_bf969de3835e/short.mp4` | 7107370 | `sha256:f6a8adeb20906080c6ae293c815167ac20d0b67cf50de002789f4b92ecd2d2df` |
| render | `artifacts/clip_bf969de3835e/render_metadata.json` | 407 | `sha256:694e6acfefcde1c1a06cb97f53434dd972fe3d0e0e9dc63d5d6f3a4b7128cb27` |
| report | `report.md` | 9328 | `sha256:cf2251dbe0d8a208bc44c8e790f1d5e6dbc3018686082453e4833e899fb44570` |

---

## 5. Executed Subprocess Commands (`commands.log`)

```bash
ffmpeg -y -f lavfi -i testsrc=duration=30:size=640x360:rate=30 -f lavfi -i flite=text=This original technical demonstration explains reliable video processing with speech transcription scene detection deterministic selection accurate subtitles audio normalization and vertical rendering. Every spoken word receives a timestamp so an independent verifier can prove synchronization selection boundaries frame rate loudness and artifact integrity. This final sentence provides enough continuous speech for a complete technical short. -af apad -c:v libx264 -c:a aac -pix_fmt yuv420p -t 30 runs/run_t3_golden/scratch/source_original_cc0.mp4
ffprobe -v error -show_format -show_streams -of json /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/ingest/source.mp4
ffmpeg -y -nostdin -v error -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/ingest/source.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/transcribe/audio_16k.wav
/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/.venv/bin/python -m cortes.whisper_worker --audio /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/transcribe/audio_16k.wav --model small --device cuda --compute-type float16
/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/.venv/bin/scenedetect -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/ingest/source.mp4 -o /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/scenes detect-content -t 27.0 -m 0.6s list-scenes
ffprobe -v error -show_entries format=duration -of json /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/ingest/source.mp4
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/ingest/source.mp4
ffmpeg -y -ss 0.0 -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/ingest/source.mp4 -t 26.12 -c copy -avoid_negative_ts make_zero runs/run_t3_golden/artifacts/cut/clip.mp4
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 runs/run_t3_golden/artifacts/cut/clip.mp4
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/cut/clip.mp4 -af loudnorm=I=-14.0:LRA=11.0:TP=-0.1:print_format=json -f null -
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/cut/clip.mp4 -af loudnorm=I=-14.0:LRA=11.0:TP=-0.1:measured_I=-21.40:measured_LRA=2.10:measured_TP=-0.85:measured_thresh=-31.40:offset=1.84:linear=true -c:v copy -c:a aac -b:a 192k /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/audio/audio_normalized.mp4
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/audio/audio_normalized.mp4 -filter_complex split[bg][fg];[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,gblur=sigma=12.0,scale=1080:1920[blurred];[fg]scale=1080:-2[scaled_fg];[blurred][scaled_fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,drawbox=x=40:y=60:w=1000:h=100:color=black@0.6:t=fill,drawtext=text='ANALYTICAL OVERLAY | VIRAL HOOK SCORE\: 9.8':x=60:y=95:fontsize=36:fontcolor=yellow,subtitles=/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/subtitles/subtitles.ass -c:v h264_nvenc -preset p4 -c:a aac -b:a 192k -pix_fmt yuv420p /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden/artifacts/clip_bf969de3835e/short.mp4
```

---

## 6. Final Integrity Verdict

- **Overall Status**: `PASSED`
- **Total Checks Passed**: `22/22`
