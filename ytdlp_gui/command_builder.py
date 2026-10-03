from __future__ import annotations

from .dependencies import ffmpeg_location_arg
from .models import Container, DownloadMode, DownloadOptions, VideoCodec


PROGRESS_PREFIX = "__YTDLP_PROGRESS__"
OUTPUT_PREFIX = "__YTDLP_OUTPUT__"

_CODEC_FILTERS = {
    VideoCodec.H264: "[vcodec^=avc1]",
    VideoCodec.VP9: "[vcodec^=vp9]",
    VideoCodec.AV1: "[vcodec^=av01]",
}


def _quality_filter(quality: str, fallback_lower: bool) -> str:
    if quality == "Best":
        return ""
    height = int(quality.removesuffix("p"))
    operator = "<=" if fallback_lower else "="
    return f"[height{operator}{height}]"


def _video_selector(options: DownloadOptions) -> str:
    quality = _quality_filter(options.quality, options.fallback_lower)
    selected_codec = _CODEC_FILTERS.get(options.codec, "")

    def pair(video_extra: str = "", audio: str = "bestaudio") -> str:
        return f"bestvideo{quality}{selected_codec}{video_extra}+{audio}"

    def combined(extra: str = "") -> str:
        return f"best{quality}{selected_codec}{extra}"

    def pair_or_combined(video_extra: str = "", audio: str = "bestaudio", combined_extra: str | None = None) -> str:
        return f"{pair(video_extra, audio)}/{combined(video_extra if combined_extra is None else combined_extra)}"

    if options.container is Container.MP4:
        if options.codec is VideoCodec.AUTO:
            preferred = f"bestvideo{quality}[vcodec^=avc1][ext=mp4]+bestaudio[acodec^=mp4a][ext=m4a]"
            preferred_combined = f"best{quality}[vcodec^=avc1][ext=mp4]"
            compatible = f"bestvideo{quality}[ext=mp4]+bestaudio[ext=m4a]"
            compatible_combined = f"best{quality}[ext=mp4]"
            return f"{preferred}/{preferred_combined}/{compatible}/{compatible_combined}/{pair_or_combined()}"
        return f"{pair_or_combined('[ext=mp4]', 'bestaudio[ext=m4a]')}/{pair_or_combined()}"

    if options.container is Container.WEBM:
        if options.codec is VideoCodec.AUTO:
            preferred = f"bestvideo{quality}[ext=webm]+bestaudio[ext=webm]"
            return f"{preferred}/best{quality}[ext=webm]/{pair_or_combined()}"
        return f"{pair_or_combined('[ext=webm]', 'bestaudio[ext=webm]')}/{pair_or_combined()}"

    return pair_or_combined()


def build_download_args(options: DownloadOptions) -> list[str]:
    section = options.section_start is not None or options.section_end is not None
    output_template = "%(title)s.%(ext)s"
    if section:
        start = format(options.section_start or 0, ".3f").rstrip("0").rstrip(".") or "0"
        end = format(options.section_end, ".3f").rstrip("0").rstrip(".") if options.section_end is not None else "inf"
        output_template = f"%(title)s [clip {start}-{end}].%(ext)s"
    args = [
        "--no-playlist",
        "--newline",
        "--windows-filenames",
        "--no-overwrites",
        "--no-color",
        "--progress-template",
        f"download:{PROGRESS_PREFIX}%(info.vcodec)s|%(progress)j",
        "--print",
        f"after_move:{OUTPUT_PREFIX}%(filepath)s",
        "--no-simulate",
        "--progress",
        "-P",
        str(options.output_dir),
        "-o",
        output_template,
    ]

    if section:
        args += ["--download-sections", f"*{start}-{end}"]
        if options.precise_cuts and options.mode is DownloadMode.VIDEO:
            args.append("--force-keyframes-at-cuts")

    ffmpeg_location = ffmpeg_location_arg(options.ffmpeg_path)
    if ffmpeg_location:
        args += ["--ffmpeg-location", ffmpeg_location]

    if options.mode is DownloadMode.AUDIO:
        audio_format = options.audio_format.lower()
        if audio_format == "best":
            args += ["-f", "bestaudio/best"]
        else:
            native = {
                "m4a": "bestaudio[ext=m4a]/bestaudio/best",
                "opus": "bestaudio[acodec^=opus]/bestaudio/best",
            }.get(audio_format, "bestaudio/best")
            args += ["-f", native, "-x", "--audio-format", audio_format]
            if options.audio_bitrate != "Best/default" and audio_format in {"mp3", "m4a", "opus"}:
                args += ["--audio-quality", options.audio_bitrate.replace(" kbps", "K")]
    else:
        args += ["-f", _video_selector(options)]
        merge_format = {
            Container.MP4: "mp4",
            Container.MKV: "mkv",
            Container.WEBM: "webm",
        }.get(options.container)
        if merge_format:
            args += ["--merge-output-format", merge_format]

    args.append(options.url)
    return args


def build_metadata_args(url: str) -> list[str]:
    return ["--no-playlist", "--skip-download", "--dump-single-json", url]


def display_command(program: str, args: list[str]) -> str:
    def quote(value: str) -> str:
        if not value or any(char.isspace() for char in value):
            return '"' + value.replace('"', '\\"') + '"'
        return value

    return " ".join(quote(item) for item in [program, *args])
