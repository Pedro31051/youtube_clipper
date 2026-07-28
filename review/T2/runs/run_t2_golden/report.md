# Execution & Verification Report — Run `run_t2_golden`

**Generated At**: `N/A`  
**Verification Verdict**: `UNVERIFIED`

---

## 1. Run Metadata Summary

| Attribute | Value |
|---|---|
| **Run ID** | `run_t2_golden` |
| **Video ID** | `unknown` |
| **Clip ID** | `null` |
| **Agent** | `worker` |
| **Start Time (UTC)** | `2026-07-27T15:47:35.454865+00:00` |
| **End Time (UTC)** | `2026-07-27T15:49:13.190310+00:00` |
| **Total Events** | `33` |
| **Total Duration (ms)** | `286923.54` |

---

## 2. Stage Execution Log (`events.jsonl`)

| Seq | Stage | Attempt | Tool / Command | Exit Code | Outcome | Duration (ms) |
|---|---|---|---|---|---|---|
| 1 | env | 1 | `ffmpeg -y -f lavfi -i testsrc=duration=30:size=640x360:ra...` | 0 | ok | 2334.69 |
| 2 | ingest | 1 | `ffprobe -v error -show_format -show_streams -of json /hom...` | 0 | ok | 76.07 |
| 3 | ingest | 1 | `python` | 0 | ok | 83.13 |
| 4 | ingest | 1 | `python` | 0 | ok | 86.73 |
| 5 | transcribe | 1 | `ffmpeg -y -nostdin -v error -i /home/pedrofelipealvesroch...` | 0 | ok | 92.9 |
| 6 | transcribe | 1 | `python` | 0 | ok | 98.7 |
| 7 | transcribe | 1 | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_cli...` | 0 | ok | 3331.2 |
| 8 | transcribe | 1 | `python` | 0 | ok | 3337.65 |
| 9 | transcribe | 1 | `python` | 0 | ok | 3446.2 |
| 10 | scenes | 1 | `/home/pedrofelipealvesrocha/teamwork_projects/youtube_cli...` | 0 | ok | 1204.25 |
| 11 | scenes | 1 | `ffprobe -v error -show_entries format=duration -of json /...` | 0 | ok | 73.57 |
| 12 | scenes | 1 | `python` | 0 | ok | 1289.21 |
| 13 | select | 1 | `python` | 0 | ok | 5.89 |
| 14 | cut | 1 | `ffprobe -v error -show_entries format=duration -of defaul...` | 0 | ok | 74.33 |
| 15 | cut | 1 | `ffmpeg -y -ss 0.0 -i /home/pedrofelipealvesrocha/teamwork...` | 0 | ok | 86.97 |
| 16 | cut | 1 | `ffprobe -v error -show_entries format=duration -of defaul...` | 0 | ok | 72.44 |
| 17 | cut | 1 | `python` | 0 | ok | 250.71 |
| 18 | cut | 1 | `python` | 0 | ok | 254.87 |
| 19 | subtitles | 1 | `python` | 0 | ok | 0.03 |
| 20 | subtitles | 1 | `python` | 0 | ok | 0.05 |
| 21 | subtitles | 1 | `python` | 0 | ok | 0.04 |
| 22 | subtitles | 1 | `python` | 0 | ok | 0.04 |
| 23 | subtitles | 1 | `python` | 0 | ok | 11.49 |
| 24 | subtitles | 1 | `python` | 0 | ok | 14.65 |
| 25 | audio | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 896.32 |
| 26 | audio | 1 | `python` | 0 | ok | 0.31 |
| 27 | audio | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 2436.57 |
| 28 | audio | 1 | `python` | 0 | ok | 3348.94 |
| 29 | audio | 1 | `python` | 0 | ok | 3356.04 |
| 30 | render | 1 | `python` | 0 | ok | 0.1 |
| 31 | render | 1 | `ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealves...` | 0 | ok | 86875.92 |
| 32 | render | 1 | `python` | 0 | ok | 86885.96 |
| 33 | render | 1 | `python` | 0 | ok | 86897.57 |

---

## 3. Verification Check Results (`verify_result.json`)

| Check ID | Status | Measured | Expected | Evidence Path |
|---|---|---|---|---|
| N/A | UNVERIFIED | N/A | N/A | N/A |

---

## 4. Produced Artifacts & Cryptographic Signatures

| Stage | Path | Bytes | SHA-256 Hash |
|---|---|---|---|
| env | `scratch/LICENSE_PROOF.md` | 386 | `sha256:c14eb31b440a6758aa15020d8da39c4d9ea832bae30fd4de483db24259d80bce` |
| ingest | `artifacts/ingest/source.mp4` | 335176 | `sha256:243f1d82766636fd1e24c69aa6fc81ff42b4bfd0923878692c5c828d5db1bd5f` |
| ingest | `artifacts/ingest/metadata.json` | 424 | `sha256:dcd95916bd894fcf0eadb768659675365c3a54479649a526f743a8b35aa278cf` |
| transcribe | `artifacts/transcribe/audio_16k.wav` | 962638 | `sha256:2a01b2aa1fa0460efad600dcba4de506b4a5c14a016bfeb14d3fb6d4a97a6c2e` |
| transcribe | `artifacts/transcribe/transcript.json` | 20145 | `sha256:f1343ab4088bd82601bd867593b8ee6916d4befd299d55f0b2d41c1835242c29` |
| scenes | `artifacts/scenes/scenes.json` | 1095 | `sha256:982473db71f5c17a67453f5b5a85c284c40e14a4fd0bd7ef66938ce5147990ca` |
| select | `artifacts/select/selection.json` | 182 | `sha256:bf969de3835e84cf3dfd0276b61f4080ee4f00b7d6b52584d0a9d9e6a4435594` |
| cut | `artifacts/cut/clip.mp4` | 312378 | `sha256:fbfbdd3f0a0550fc032b57b41866c2c66edd54417f3de33b28dda04712d9d9b4` |
| cut | `artifacts/cut/cut_metadata.json` | 157 | `sha256:cdd865e05fc8cf3b4848784da3dc2dadedc821b9662e5fa1fc94e34e004a1043` |
| subtitles | `artifacts/subtitles/subtitles.ass` | 3793 | `sha256:6e8cc6e717b55a741eab52167670810ed3afe2514f142783d223eba26fe8b7e2` |
| subtitles | `artifacts/subtitles/subtitle_mapping.json` | 13123 | `sha256:99e94c9340655bb742c48f9aa33a594a957863f0c557b22eae5ec270bd5d74d4` |
| audio | `artifacts/audio/audio_normalized.mp4` | 841497 | `sha256:b5dff7b74b28f858bc2365acbb41ddf39895bf73ad277927df71be129a605f52` |
| audio | `artifacts/audio/audio_stats.json` | 405 | `sha256:82bb3ad1a9e87c2dcfbc13aa8dcaf5040dcc2f6509758fd213518c5b817b02a8` |
| render | `artifacts/clip_bf969de3835e/short.mp4` | 2409274 | `sha256:8b3563a1f04bed36c710f3ccab0f868339a2accb356ea67d7454ae6f0d743a6d` |
| render | `artifacts/clip_bf969de3835e/render_metadata.json` | 266 | `sha256:799f7c124a2b1cb1f9e1419eef140d08e02346912d612b8a634648017cdf9802` |

---

## 5. Executed Subprocess Commands (`commands.log`)

```bash
ffmpeg -y -f lavfi -i testsrc=duration=30:size=640x360:rate=30 -f lavfi -i flite=text=This original technical demonstration explains reliable video processing with speech transcription scene detection deterministic selection accurate subtitles audio normalization and vertical rendering. Every spoken word receives a timestamp so an independent verifier can prove synchronization selection boundaries frame rate loudness and artifact integrity. This final sentence provides enough continuous speech for a complete technical short. -af apad -c:v libx264 -c:a aac -pix_fmt yuv420p -t 30 runs/run_t2_golden/scratch/source_original_cc0.mp4
ffprobe -v error -show_format -show_streams -of json /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/ingest/source.mp4
ffmpeg -y -nostdin -v error -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/ingest/source.mp4 -vn -ac 1 -ar 16000 -c:a pcm_s16le /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/transcribe/audio_16k.wav
/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/.venv/bin/python -m cortes.whisper_worker --audio /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/transcribe/audio_16k.wav --model small --device cuda --compute-type float16
/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/.venv/bin/scenedetect -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/ingest/source.mp4 -o /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/scenes detect-content -t 27.0 -m 0.6s list-scenes
ffprobe -v error -show_entries format=duration -of json /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/ingest/source.mp4
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/ingest/source.mp4
ffmpeg -y -ss 0.0 -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/ingest/source.mp4 -t 26.12 -c copy -avoid_negative_ts make_zero runs/run_t2_golden/artifacts/cut/clip.mp4
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 runs/run_t2_golden/artifacts/cut/clip.mp4
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/cut/clip.mp4 -af loudnorm=I=-14.0:LRA=11.0:TP=-0.1:print_format=json -f null -
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/cut/clip.mp4 -af loudnorm=I=-14.0:LRA=11.0:TP=-0.1:measured_I=-21.40:measured_LRA=2.10:measured_TP=-0.85:measured_thresh=-31.40:offset=1.84:linear=true -c:v copy -c:a aac -b:a 192k /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/audio/audio_normalized.mp4
ffmpeg -y -nostdin -hide_banner -i /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/audio/audio_normalized.mp4 -filter_complex split[bg][fg];[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:10[blurred];[fg]scale=1080:-2[scaled_fg];[blurred][scaled_fg]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2,subtitles=/home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/subtitles/subtitles.ass -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k -pix_fmt yuv420p /home/pedrofelipealvesrocha/teamwork_projects/youtube_clipper/runs/run_t2_golden/artifacts/clip_bf969de3835e/short.mp4
```

---

## 6. Final Integrity Verdict

- **Overall Status**: `UNVERIFIED`
- **Total Checks Passed**: `0/0`
