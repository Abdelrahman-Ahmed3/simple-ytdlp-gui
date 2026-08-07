from __future__ import annotations


def friendly_error(output: str, exit_code: int) -> str:
    text = output.lower()
    checks = (
        (("requested format is not available", "format is not available"), "The selected quality, codec, or container combination is unavailable for this video."),
        (("ffmpeg not found", "ffprobe and ffmpeg not found", "ffmpeg is not installed"), "FFmpeg is required for this operation but could not be found. Select it in Settings."),
        (("unsupported url", "is not a valid url"), "The URL is invalid or is not supported by this version of yt-dlp."),
        (("video unavailable", "this video is unavailable", "private video"), "The video is unavailable or private."),
        (("sign in to confirm", "cookies", "login required", "authentication"), "This site requires authentication or browser cookies. V1 does not include cookie importing."),
        (("unable to download webpage", "network is unreachable", "connection refused", "timed out", "temporary failure"), "A network error prevented yt-dlp from reaching the site."),
        (("update to a nightly", "please update", "yt-dlp is out of date"), "yt-dlp may be outdated. Use Tools → Check for yt-dlp updates, then try again."),
    )
    for needles, message in checks:
        if any(needle in text for needle in needles):
            return message
    return f"yt-dlp stopped with exit code {exit_code}. See technical details below."
