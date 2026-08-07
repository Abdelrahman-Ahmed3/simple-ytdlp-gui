from pathlib import Path

from ytdlp_gui.command_builder import PROGRESS_PREFIX, build_download_args
from ytdlp_gui.models import Container, DownloadMode, DownloadOptions, VideoCodec


def options(**changes: object) -> DownloadOptions:
    values = {
        "url": "https://example.com/watch?v=abc",
        "output_dir": Path("downloads"),
        "mode": DownloadMode.VIDEO,
        "quality": "1080p",
        "codec": VideoCodec.H264,
        "container": Container.MP4,
    }
    values.update(changes)
    return DownloadOptions(**values)


def argument_after(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


def test_exact_h264_mp4_selector_keeps_exact_height_and_codec() -> None:
    args = build_download_args(options())
    selector = argument_after(args, "-f")
    assert "[height=1080]" in selector
    assert "[height<=1080]" not in selector
    assert "[vcodec^=avc1]" in selector
    assert argument_after(args, "--merge-output-format") == "mp4"


def test_lower_fallback_is_only_added_when_requested() -> None:
    args = build_download_args(options(fallback_lower=True))
    assert "[height<=1080]" in argument_after(args, "-f")


def test_auto_mp4_prefers_h264_and_aac_without_forcing_them() -> None:
    args = build_download_args(options(codec=VideoCodec.AUTO))
    selector = argument_after(args, "-f")
    assert selector.startswith("bestvideo[height=1080][vcodec^=avc1][ext=mp4]+bestaudio[acodec^=mp4a][ext=m4a]")
    assert selector.endswith("/bestvideo[height=1080]+bestaudio/best[height=1080]")


def test_video_selector_has_same_quality_combined_stream_fallback() -> None:
    args = build_download_args(options(container=Container.AUTO, codec=VideoCodec.VP9))
    selector = argument_after(args, "-f")
    assert selector == "bestvideo[height=1080][vcodec^=vp9]+bestaudio/best[height=1080][vcodec^=vp9]"


def test_best_audio_does_not_add_conversion() -> None:
    args = build_download_args(options(mode=DownloadMode.AUDIO, audio_format="Best"))
    assert "-x" not in args
    assert argument_after(args, "-f") == "bestaudio/best"


def test_mp3_conversion_and_bitrate_are_explicit() -> None:
    args = build_download_args(
        options(mode=DownloadMode.AUDIO, audio_format="MP3", audio_bitrate="192 kbps")
    )
    assert "-x" in args
    assert argument_after(args, "--audio-format") == "mp3"
    assert argument_after(args, "--audio-quality") == "192K"


def test_progress_template_is_machine_readable_and_url_is_last() -> None:
    item = options()
    args = build_download_args(item)
    assert PROGRESS_PREFIX in argument_after(args, "--progress-template")
    assert "--no-simulate" in args
    assert args.index("--progress") > args.index("--print")
    assert args[-1] == item.url
