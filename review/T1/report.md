# Execution & Verification Report — Run `run_t1_20260727T193302Z`

**Generated At**: `2026-07-27T19:33:06.677704+00:00`  
**Verification Verdict**: `PASSED`

---

## 1. Run Metadata Summary

| Attribute | Value |
|---|---|
| **Run ID** | `run_t1_20260727T193302Z` |
| **Video ID** | `unknown` |
| **Clip ID** | `null` |
| **Agent** | `worker_t1` |
| **Start Time (UTC)** | `2026-07-27T19:33:06.396869+00:00` |
| **End Time (UTC)** | `2026-07-27T19:33:06.677704+00:00` |
| **Total Events** | `9` |
| **Total Duration (ms)** | `520.03` |

---

## 2. Stage Execution Log (`events.jsonl`)

| Seq | Stage | Attempt | Tool / Command | Exit Code | Outcome | Duration (ms) |
|---|---|---|---|---|---|---|
| 1 | env | 1 | `python3 --version` | 0 | ok | 3.13 |
| 2 | env | 1 | `ffmpeg -version` | 0 | ok | 67.56 |
| 3 | env | 1 | `ffprobe -version` | 0 | ok | 64.54 |
| 4 | env | 1 | `python3 -c "import soundfile"` | 0 | ok | 53.97 |
| 5 | env | 1 | `fc-list | grep -Eci "inter|roboto|noto"` | 0 | ok | 12.46 |
| 6 | env | 1 | `nvidia-smi --query-gpu=name,memory.total --format=csv` | 0 | ok | 31.7 |
| 7 | env | 1 | `df -B1G --output=avail . | tail -1` | 0 | ok | 3.13 |
| 8 | env | 1 | `git --version` | 0 | ok | 2.73 |
| 9 | env | 1 | `python` | 0 | ok | 280.81 |

---

## 3. Verification Check Results (`verify_result.json`)

| Check ID | Status | Measured | Expected | Evidence Path |
|---|---|---|---|---|
| `python_version` | PASS | Python 3.12.3 | recorded final attempt satisfies the T1 criterion | `env_check.json` |
| `ffmpeg_libraries` | PASS | ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023 the FFmpeg developers
built with gcc 13 (Ubuntu 13.2.0-23ubuntu3)
configuration: --prefix=/usr --extra-version=3ubuntu5 --toolchain=hardened --libdir=/usr/lib/x86_64-linux-gnu --incdir=/usr/include/x86_64-linux-gnu --arch=amd64 --enable-gpl --disable-stripping --disable-omx --enable-gnutls --enable-libaom --enable-libass --enable-libbs2b --enable-libcaca --enable-libcdio --enable-libcodec2 --enable-libdav1d --enable-libflite --enable-libfontconfig --enable-libfreetype --enable-libfribidi --enable-libglslang --enable-libgme --enable-libgsm --enable-libharfbuzz --enable-libmp3lame --enable-libmysofa --enable-libopenjpeg --enable-libopenmpt --enable-libopus --enable-librubberband --enable-libshine --enable-libsnappy --enable-libsoxr --enable-libspeex --enable-libtheora --enable-libtwolame --enable-libvidstab --enable-libvorbis --enable-libvpx --enable-libwebp --enable-libx265 --enable-libxml2 --enable-libxvid --enable-libzimg --enable-openal --enable-opencl --enable-opengl --disable-sndio --enable-libvpl --disable-libmfx --enable-libdc1394 --enable-libdrm --enable-libiec61883 --enable-chromaprint --enable-frei0r --enable-ladspa --enable-libbluray --enable-libjack --enable-libpulse --enable-librabbitmq --enable-librist --enable-libsrt --enable-libssh --enable-libsvtav1 --enable-libx264 --enable-libzmq --enable-libzvbi --enable-lv2 --enable-sdl2 --enable-libplacebo --enable-librav1e --enable-pocketsphinx --enable-librsvg --enable-libjxl --enable-shared
libavutil      58. 29.100 / 58. 29.100
libavcodec     60. 31.102 / 60. 31.102
libavformat    60. 16.100 / 60. 16.100
libavdevice    60.  3.100 / 60.  3.100
libavfilter     9. 12.100 /  9. 12.100
libswscale      7.  5.100 /  7.  5.100
libswresample   4. 12.100 /  4. 12.100
libpostproc    57.  3.100 / 57.  3.100 | recorded final attempt satisfies the T1 criterion | `env_check.json` |
| `ffprobe_available` | PASS | ffprobe version 6.1.1-3ubuntu5 Copyright (c) 2007-2023 the FFmpeg developers
built with gcc 13 (Ubuntu 13.2.0-23ubuntu3)
configuration: --prefix=/usr --extra-version=3ubuntu5 --toolchain=hardened --libdir=/usr/lib/x86_64-linux-gnu --incdir=/usr/include/x86_64-linux-gnu --arch=amd64 --enable-gpl --disable-stripping --disable-omx --enable-gnutls --enable-libaom --enable-libass --enable-libbs2b --enable-libcaca --enable-libcdio --enable-libcodec2 --enable-libdav1d --enable-libflite --enable-libfontconfig --enable-libfreetype --enable-libfribidi --enable-libglslang --enable-libgme --enable-libgsm --enable-libharfbuzz --enable-libmp3lame --enable-libmysofa --enable-libopenjpeg --enable-libopenmpt --enable-libopus --enable-librubberband --enable-libshine --enable-libsnappy --enable-libsoxr --enable-libspeex --enable-libtheora --enable-libtwolame --enable-libvidstab --enable-libvorbis --enable-libvpx --enable-libwebp --enable-libx265 --enable-libxml2 --enable-libxvid --enable-libzimg --enable-openal --enable-opencl --enable-opengl --disable-sndio --enable-libvpl --disable-libmfx --enable-libdc1394 --enable-libdrm --enable-libiec61883 --enable-chromaprint --enable-frei0r --enable-ladspa --enable-libbluray --enable-libjack --enable-libpulse --enable-librabbitmq --enable-librist --enable-libsrt --enable-libssh --enable-libsvtav1 --enable-libx264 --enable-libzmq --enable-libzvbi --enable-lv2 --enable-sdl2 --enable-libplacebo --enable-librav1e --enable-pocketsphinx --enable-librsvg --enable-libjxl --enable-shared
libavutil      58. 29.100 / 58. 29.100
libavcodec     60. 31.102 / 60. 31.102
libavformat    60. 16.100 / 60. 16.100
libavdevice    60.  3.100 / 60.  3.100
libavfilter     9. 12.100 /  9. 12.100
libswscale      7.  5.100 /  7.  5.100
libswresample   4. 12.100 /  4. 12.100
libpostproc    57.  3.100 / 57.  3.100 | recorded final attempt satisfies the T1 criterion | `env_check.json` |
| `soundfile_import` | PASS | (empty stdout) | recorded final attempt satisfies the T1 criterion | `env_check.json` |
| `fonts_available` | PASS | 271 | recorded final attempt satisfies the T1 criterion | `env_check.json` |
| `nvidia_gpu` | PASS | name, memory.total [MiB]
Tesla T4, 15360 MiB | recorded final attempt satisfies the T1 criterion | `env_check.json` |
| `disk_available_gib` | PASS | 20 | recorded final attempt satisfies the T1 criterion | `env_check.json` |
| `git_available` | PASS | git version 2.43.0 | recorded final attempt satisfies the T1 criterion | `env_check.json` |

---

## 4. Produced Artifacts & Cryptographic Signatures

| Stage | Path | Bytes | SHA-256 Hash |
|---|---|---|---|
| env | `env_check.json` | 10374 | `sha256:e405581fbb9ba7ebf4bbaf296e3456d2f60b2d62143565614627032a2490de5c` |

---

## 5. Executed Subprocess Commands (`commands.log`)

```bash
python3 --version
ffmpeg -version
ffprobe -version
python3 -c "import soundfile"
fc-list | grep -Eci "inter|roboto|noto"
nvidia-smi --query-gpu=name,memory.total --format=csv
df -B1G --output=avail . | tail -1
git --version
```

---

## 6. Final Integrity Verdict

- **Overall Status**: `PASSED`
- **Total Checks Passed**: `8/8`
