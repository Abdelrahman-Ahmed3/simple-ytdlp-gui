# yt-dlp GUI

A compact desktop GUI frontend for [yt-dlp](https://github.com/yt-dlp/yt-dlp). It makes common video and audio downloads accessible without requiring users to remember command-line options, while leaving extraction and site support entirely to yt-dlp.

## Features

- Video or audio-only downloads from any URL supported by yt-dlp
- Download a section using start/end timestamps, with optional precise video cuts
- Exact video quality selection, with an explicit optional lower-resolution fallback
- Source stream preferences for H.264/AVC, VP9, and AV1 without automatic video transcoding
- MP4, MKV, WebM, or automatic output container selection
- MP3, M4A, Opus, FLAC, and WAV audio conversion with optional lossy bitrate settings
- Asynchronous format inspection and downloads, progress, speed, size, ETA, and cancellation
- Clear error messages with copyable technical details and a separate debug log
- Automatic yt-dlp and FFmpeg discovery, first-use installation, configurable executable paths, and yt-dlp update controls
- Persistent choices and output folder through Qt settings

V1 intentionally handles one URL at a time and does not include playlists, queues, cookies, subtitles, account management, or DRM/access-control bypass features.

## Requirements

- Windows 10 or later (the code is portable, but V1 is designed and tested for Windows)
- Python 3.10+
- An internet connection the first time the application installs yt-dlp or FFmpeg

The packaged GUI can start with neither yt-dlp nor FFmpeg installed. When an operation first needs a missing tool, the application offers to download it into its private local-application-data tools folder and automatically resumes the original action afterward. Existing configured or system `PATH` installations are still detected.

yt-dlp is downloaded from its official GitHub release. FFmpeg itself publishes source code and links Windows users to compiled build providers; this app uses the gyan.dev release essentials build and its GitHub mirror. The FFmpeg archive's published SHA-256 checksum is verified, only `ffmpeg.exe` and `ffprobe.exe` are extracted, and the archive is deleted afterward. The essentials build is GPLv3-licensed. See [FFmpeg's download page](https://ffmpeg.org/download.html) and [gyan.dev's Windows builds](https://www.gyan.dev/ffmpeg/builds/).

## Run from source

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m ytdlp_gui
```

Paste a URL, use **Check formats** to inspect streams, select the desired settings, choose an output folder, and click **Download**.

For clips, enable **Download only a section** and enter a start and/or end time. Accepted formats are seconds (`90`), `MM:SS` (`1:30`), and `HH:MM:SS` (`01:02:30`), with up to three decimal places for seconds. A blank start means the beginning; a blank end means the end of the video. The end must be later than the start. Sections work in both video and audio-only modes and require FFmpeg, which the app can install when needed.

Clips include their range in the filename, so different sections and full downloads stay separate. The section choice and timestamps are remembered. **Precise video cuts** re-encodes video for cleaner cut boundaries and is slower; otherwise cuts may align with nearby keyframes. Section downloads use yt-dlp's [download-sections support](https://github.com/yt-dlp/yt-dlp#download-options); transfer efficiency depends on the site's stream and seeking support.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

The automated suite covers command construction, exact-versus-fallback quality behavior, format/codec analysis, progress parsing, validation, and common error classification. Network download checks should use media you are permitted to download; availability and format inventories can change independently of this project.

## Build a Windows executable

Install development requirements, then run from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

The single-file application will be created as `dist\yt-dlp-gui-v0.1.7.exe`. yt-dlp and FFmpeg are deliberately not frozen into the executable; the application installs current copies into its private tools folder when required. This keeps the shared GUI executable small enough to distribute and avoids permanently embedding outdated tool versions.

## Selection behavior

- A named quality such as 1080p uses an exact `height=1080` filter.
- **Allow closest lower resolution** changes that to `height<=1080`; it is never enabled implicitly.
- Codec preferences filter existing source streams (`avc1`, `vp9`, or `av01`). They do not cause video transcoding.
- MP4 in Auto codec mode tries H.264 video plus AAC/M4A audio first, then other MP4-native streams, before a same-quality generic stream combination.
- Audio **Best** keeps the best source audio without forcing extraction/conversion. Other audio formats use FFmpeg only as needed by yt-dlp's audio postprocessor.

yt-dlp command output is available under **Tools → Debug log**. Commands are launched directly with program/argument arrays through `QProcess`; no shell command is constructed.

## Disclaimer

Users are responsible for complying with applicable laws and the terms of service of websites they access. Only download media you are permitted to download. This project does not bypass DRM, paywalls, or access controls.
