# Execution & Verification Report — Run `run_t3_golden_v5`

**Generated At**: `2026-07-27T18:34:15.851260+00:00`  
**Verification Verdict**: `PASSED`

---

## 1. Run Metadata Summary

| Attribute | Value |
|---|---|
| **Run ID** | `run_t3_golden_v5` |
| **Video ID** | `unknown` |
| **Clip ID** | `clip_f6be54249092` |
| **Agent** | `worker` |
| **Start Time (UTC)** | `2026-07-27T18:19:59.361247+00:00` |
| **End Time (UTC)** | `2026-07-27T18:20:22.401598+00:00` |
| **Total Events** | `38` |
| **Total Duration (ms)** | `63861.27` |

---

## 2. Stage Execution Log (`events.jsonl`)

| Seq | Stage | Attempt | Tool / Command | Exit Code | Outcome | Duration (ms) |
|---|---|---|---|---|---|---|
| 1 | env | 1 | `ffmpeg -y -f lavfi -i testsrc=duration=30:size=640x360:ra...` | 0 | ok | 2450.03 |
| 2 | env | 1 | `ffmpeg -y -f lavfi -i flite=textfile=runs/run_t3_golden_v...` | 0 | ok | 117.11 |
| 3 | env | 1 | `python` | 0 | ok | 2578.31 |
| 4 | ingest | 1 | `ffprobe -v error -show_format -show_streams -of json /hom...` | 0 | ok | 73.47 |
| 5 | ingest | 1 | `python` | 0 | ok | 79.75 |
| 6 | ingest | 1 | `python` | 0 | ok | 83.3 |
| 7 | transcribe | 1 | `ffmpeg -y -nostdin -v error -i /home/pedrofelipealvesroch...` | 0 | ok | 95.91 |
| 8 | transcribe | 1 | `python` | 0 | ok | 101.65 |
| 9 | transcribe | 1 | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_cli...` | 0 | ok | 3423.0 |
| 10 | transcribe | 1 | `python` | 0 | ok | 3428.81 |
| 11 | transcribe | 1 | `python` | 0 | ok | 3540.25 |
| 12 | scenes | 1 | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_cli...` | 0 | ok | 1206.67 |
| 13 | scenes | 1 | `ffprobe -v error -show_entries format=duration -of json /...` | 0 | ok | 79.12 |
| 14 | scenes | 1 | `python` | 0 | ok | 1298.95 |
| 15 | select | 1 | `python` | 0 | ok | 6.31 |
| 16 | cut | 1 | `ffprobe -v error -show_entries format=duration -of defaul...` | 0 | ok | 76.99 |
| 17 | cut | 1 | `ffmpeg -y -ss 0.0 -i /home/pedrofelipealvesrocha/teamwork...` | 0 | ok | 86.15 |
| 18 | cut | 1 | `ffprobe -v error -show_entries format=duration -of defaul...` | 0 | ok | 73.52 |
| 19 | cut | 1 | `python` | 0 | ok | 253.54 |
| 20 | cut | 1 | `python` | 0 | ok | 257.78 |
| 21 | subtitles | 1 | `python` | 0 | ok | 0.03 |
| 22 | subtitles | 1 | `python` | 0 | ok | 0.05 |
| 23 | subtitles | 1 | `python` | 0 | ok | 0.04 |
| 24 | subtitles | 1 | `python` | 0 | ok | 0.04 |
| 25 | subtitles | 1 | `python` | 0 | ok | 13.4 |
| 26 | subtitles | 1 | `python` | 0 | ok | 16.86 |
| 27 | audio | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 943.49 |
| 28 | audio | 1 | `python` | 0 | ok | 0.37 |
| 29 | audio | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 2505.91 |
| 30 | audio | 1 | `python` | 0 | ok | 3463.71 |
| 31 | audio | 1 | `python` | 0 | ok | 3470.85 |
| 32 | render | 1 | `python` | 0 | ok | 0.23 |
| 33 | render | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 944.39 |
| 34 | render | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 9778.12 |
| 35 | render | 1 | `python` | 0 | ok | 11686.37 |
| 36 | render | 1 | `python` | 0 | ok | 11721.29 |
| 37 | report | 1 | `python` | 0 | ok | 1.09 |
| 38 | report | 1 | `python` | 0 | ok | 4.41 |

---

## 3. Verification Check Results (`verify_result.json`)

| Check ID | Status | Measured | Expected | Evidence Path |
|---|---|---|---|---|
| `events_file_exists` | PASS | File exists | File exists | `events.jsonl` |
| `events_schema_valid` | PASS | Validated 38 events | Schema Version 1.0.0 valid | `events.jsonl` |
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
| `video_resolution::artifacts/clip_f6be54249092/short.mp4` | PASS | 1080x1920 | 1080x1920 | `artifacts/clip_f6be54249092/short.mp4` |
| `video_constant_fps::artifacts/clip_f6be54249092/short.mp4` | PASS | r_frame_rate=30.000000, avg_frame_rate=30.000000 | Positive constant FPS (r_frame_rate == avg_frame_rate) | `artifacts/clip_f6be54249092/short.mp4` |
| `audio_stream_count::artifacts/clip_f6be54249092/short.mp4` | PASS | 1 audio stream(s) | Exactly 1 audio stream | `artifacts/clip_f6be54249092/short.mp4` |
| `video_duration_range::artifacts/clip_f6be54249092/short.mp4` | PASS | 26.43 seconds | 20.0 <= duration <= 58.0 seconds | `artifacts/clip_f6be54249092/short.mp4` |
| `audio_lufs_loudness::artifacts/clip_f6be54249092/short.mp4` | PASS | -15.30 LUFS | [-16.0 LUFS, -13.0 LUFS] | `artifacts/clip_f6be54249092/short.mp4` |
| `editorial_metadata::artifacts/clip_f6be54249092/short.mp4` | PASS | Render metadata is valid JSON | Valid T3 render_metadata.json | `artifacts/clip_f6be54249092/render_metadata.json` |
| `editorial_narration::artifacts/clip_f6be54249092/short.mp4` | PASS | exists=True, duration=10.000s, hash_match=True, bytes_match=True, amix_proven=True | Physical narration >= 8.0s with matching hash/bytes and audited amix command | `artifacts/editorial/narration.wav` |
| `editorial_overlay::artifacts/clip_f6be54249092/short.mp4` | PASS | metadata_enabled=True, text_present=True, command_proven=True | Non-empty analytical overlay burned by drawbox/drawtext | `artifacts/clip_f6be54249092/render_metadata.json` |
| `editorial_transformation::artifacts/clip_f6be54249092/short.mp4` | PASS | requirements=['analytical_overlay', 'narration'], results={'narration': True, 'analytical_overlay': True} | Every declared T3 editorial requirement is physically proven | `artifacts/clip_f6be54249092/render_metadata.json` |
| `template_variant_unique::artifacts/clip_f6be54249092/short.mp4` | PASS | variant=variant_t3_analytical_v5, previous_five=['variant_t3_analytical_v4', 'variant_t3_analytical_v3', 'variant_t3_analytical_v1'] | Non-default variant absent from previous five renders | `artifacts/clip_f6be54249092/render_metadata.json` |
| `clip_id_binds_variant::artifacts/clip_f6be54249092/short.mp4` | PASS | declared=clip_f6be54249092, recomputed=clip_f6be54249092 | clip_id = SHA256(selection + template_variant) | `artifacts/clip_f6be54249092/render_metadata.json` |
| `selection_within_source_bounds` | PASS | start_ms=0, end_ms=26120, source_duration_ms=30000 | 0 <= start_ms < end_ms <= source_duration_ms | `artifacts/select/selection.json` |
| `subtitle_word_alignment` | PASS | All ASS events map to transcript words within +/-200 ms | Non-empty ASS; every event maps to a transcript word within +/-200 ms and remains inside the selected interval | `artifacts/subtitles/subtitles.ass` |

---

## 4. Produced Artifacts & Cryptographic Signatures

| Stage | Path | Bytes | SHA-256 Hash |
|---|---|---|---|
| env | `scratch/LICENSE_PROOF.md` | 91 | `sha256:c9ba55def8537213ff74641651d6c7c40ee0113e09b4c95433249d8c1fa21a38` |
| env | `scratch/editorial_narration.txt` | 242 | `sha256:fa64dbe5811d5bcb2ec052bb87808217f6c42461bb5594da8863db14945d21e7` |
| env | `scratch/editorial_narration.wav` | 160078 | `sha256:fc602c36bc97ae9863bca28a0a584c65fb490709cd41bc71df252edfcfe3d583` |
| ingest | `artifacts/ingest/source.mp4` | 335176 | `sha256:243f1d82766636fd1e24c69aa6fc81ff42b4bfd0923878692c5c828d5db1bd5f` |
| ingest | `artifacts/ingest/metadata.json` | 427 | `sha256:a182c99d125d42f57dcef304cdc0385b5e42d06ba42bce76e7627ebbdc469248` |
| transcribe | `artifacts/transcribe/audio_16k.wav` | 962638 | `sha256:2a01b2aa1fa0460efad600dcba4de506b4a5c14a016bfeb14d3fb6d4a97a6c2e` |
| transcribe | `artifacts/transcribe/transcript.json` | 20145 | `sha256:f1343ab4088bd82601bd867593b8ee6916d4befd299d55f0b2d41c1835242c29` |
| scenes | `artifacts/scenes/scenes.json` | 1098 | `sha256:e2dd1ef743f8c25ffd9f0ccfd496f7da5fb30ddb24221288f115e0786283b701` |
| select | `artifacts/select/selection.json` | 182 | `sha256:bf969de3835e84cf3dfd0276b61f4080ee4f00b7d6b52584d0a9d9e6a4435594` |
| cut | `artifacts/cut/clip.mp4` | 312378 | `sha256:fbfbdd3f0a0550fc032b57b41866c2c66edd54417f3de33b28dda04712d9d9b4` |
| cut | `artifacts/cut/cut_metadata.json` | 157 | `sha256:8c745005a1b45dd13b7e10585b8078cb9f308d587218c5f34f22cc8ee1e74471` |
| subtitles | `artifacts/subtitles/subtitles.ass` | 3793 | `sha256:6e8cc6e717b55a741eab52167670810ed3afe2514f142783d223eba26fe8b7e2` |
| subtitles | `artifacts/subtitles/subtitle_mapping.json` | 13123 | `sha256:72fd2ced7e14e56c186446ec91c8e8a085dd441f7561b4965da1724cf911394f` |
| audio | `artifacts/audio/audio_normalized.mp4` | 841497 | `sha256:b5dff7b74b28f858bc2365acbb41ddf39895bf73ad277927df71be129a605f52` |
| audio | `artifacts/audio/audio_stats.json` | 405 | `sha256:82bb3ad1a9e87c2dcfbc13aa8dcaf5040dcc2f6509758fd213518c5b817b02a8` |
| render | `artifacts/clip_f6be54249092/short.mp4` | 7118542 | `sha256:3e86a6ceb0ef93c4c71061abb2750f4a24cf55fd2a5cdc9f319c500a1f7865a7` |
| render | `artifacts/clip_f6be54249092/render_metadata.json` | 1325 | `sha256:bb64cbfc74906db0627dc0977f5c32de98cd2e33cc2898705247545ba22d7a36` |
| render | `artifacts/editorial/narration.wav` | 160078 | `sha256:fc602c36bc97ae9863bca28a0a584c65fb490709cd41bc71df252edfcfe3d583` |
| report | `report.md` | 11185 | `sha256:2f6cb7990854458c488fe2b25b57c8a83ee3744359bed2fc7924198c28501ca8` |

---

## 5. Executed Subprocess Commands (`commands.log`)

```bash
ffmpeg -y -f lavfi -i testsrc=duration=30:size=640x360:rate=30 -f lavfi -i flite=text=This original technical demonstration explains reliable video processing with speech transcription scene detection deterministic selection accurate subtitles audio normalization and vertical rendering. Every spoken word receives a timestamp so an independent verifier can prove synchronization selection boundaries frame rate loudness and artifact integrity. This final sentence provides enough continuous speech for a complete technical short. -af apad -c:v libx264 -c:a aac -pix_fmt yuv420p -t 30 runs/run_t3_golden_v5/scratch/source_original_cc0.mp4
ffmpeg -y -f lavfi -i flite=textfile=runs/run_t3_golden_v5/scratch/editorial_narration.txt -af apad -t 10 -c:a pcm_s16le runs/run_t3_golden_v5/scratch/editorial_narration.wav
ffprobe -v error -show_format -show_streams -of json /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/ingest/source.mp4
ffmpeg -y -nostdin -v error -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/ingest/source.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/transcribe/audio_16k.wav
/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/.venv/bin/python -m cortes.whisper_worker --audio /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/transcribe/audio_16k.wav --model small --device cuda --compute-type float16
/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/.venv/bin/scenedetect -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/ingest/source.mp4 -o /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/scenes detect-content -t 27.0 -m 0.6s list-scenes
ffprobe -v error -show_entries format=duration -of json /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/ingest/source.mp4
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/ingest/source.mp4
ffmpeg -y -ss 0.0 -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/ingest/source.mp4 -t 26.12 -c copy -avoid_negative_ts make_zero runs/run_t3_golden_v5/artifacts/cut/clip.mp4
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 runs/run_t3_golden_v5/artifacts/cut/clip.mp4
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/cut/clip.mp4 -af loudnorm=I=-14.0:LRA=11.0:TP=-0.1:print_format=json -f null -
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/cut/clip.mp4 -af loudnorm=I=-14.0:LRA=11.0:TP=-0.1:measured_I=-21.40:measured_LRA=2.10:measured_TP=-0.85:measured_thresh=-31.40:offset=1.84:linear=true -c:v copy -c:a aac -b:a 192k /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/audio/audio_normalized.mp4
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/audio/audio_normalized.mp4 -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/editorial/narration.wav -filter_complex [0:a]volume=0.35[base_audio];[1:a]volume=1.0[narration_audio];[base_audio][narration_audio]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mixed_measure];[mixed_measure]loudnorm=I=-14.0:LRA=11:TP=-1.0:print_format=json[audio_measure] -map [audio_measure] -f null -
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/audio/audio_normalized.mp4 -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/editorial/narration.wav -filter_complex split[bg][fg];[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,gblur=sigma=12.0,scale=1080:1920[blurred];[fg]scale=1080:-2[scaled_fg];[blurred][scaled_fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,drawbox=x=40:y=60:w=1000:h=100:color=black@0.6:t=fill,drawtext=text='ANALYTICAL OVERLAY | VIRAL HOOK SCORE\: 9.8':x=60:y=95:fontsize=36:fontcolor=yellow,subtitles=/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/subtitles/subtitles.ass[vout];[0:a]volume=0.35[base_audio];[1:a]volume=1.0[narration_audio];[base_audio][narration_audio]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mixed_audio];[mixed_audio]loudnorm=I=-14.0:LRA=11:TP=-1.0:measured_I=-22.09:measured_LRA=5.70:measured_TP=-1.05:measured_thresh=-32.09:offset=2.56:linear=true[aout] -map [vout] -map [aout] -c:v h264_nvenc -preset p4 -c:a aac -b:a 192k -pix_fmt yuv420p /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t3_golden_v5/artifacts/clip_f6be54249092/short.mp4
```

---

## 6. Final Integrity Verdict

- **Overall Status**: `PASSED`
- **Total Checks Passed**: `28/28`
