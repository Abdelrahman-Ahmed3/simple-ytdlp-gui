from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .models import VideoCodec


@dataclass(frozen=True)
class FormatSummary:
    title: str
    formats: tuple[dict[str, Any], ...]

    @property
    def video_heights(self) -> tuple[int, ...]:
        heights = {
            int(fmt["height"])
            for fmt in self.formats
            if fmt.get("vcodec") not in (None, "none") and fmt.get("height")
        }
        return tuple(sorted(heights, reverse=True))

    def codecs_at(self, height: int) -> set[VideoCodec]:
        result: set[VideoCodec] = set()
        for fmt in self.formats:
            if fmt.get("vcodec") in (None, "none") or fmt.get("height") != height:
                continue
            codec = str(fmt.get("vcodec", "")).lower()
            if codec.startswith("avc1"):
                result.add(VideoCodec.H264)
            elif codec.startswith(("vp9", "vp09")):
                result.add(VideoCodec.VP9)
            elif codec.startswith("av01"):
                result.add(VideoCodec.AV1)
        return result

    def supports(self, quality: str, codec: VideoCodec, fallback_lower: bool = False) -> tuple[bool, str]:
        if quality == "Best":
            if codec is VideoCodec.AUTO:
                return True, "Best available video"
            available = any(codec in self.codecs_at(height) for height in self.video_heights)
            return available, f"{codec.value} {'is available' if available else 'is not available'}"

        target = int(quality.removesuffix("p"))
        heights = [height for height in self.video_heights if height == target or fallback_lower and height <= target]
        if not heights:
            return False, f"No {quality}{' or lower' if fallback_lower else ''} video stream is available"
        if codec is VideoCodec.AUTO:
            chosen = max(heights)
            suffix = f" (using {chosen}p)" if chosen != target else ""
            return True, f"{quality} is available{suffix}"

        codec_heights = [height for height in heights if codec in self.codecs_at(height)]
        if codec_heights:
            chosen = max(codec_heights)
            suffix = f" at {chosen}p" if chosen != target else ""
            return True, f"{codec.value} is available{suffix}"
        chosen = max(heights)
        codecs = ", ".join(item.value for item in sorted(self.codecs_at(chosen), key=lambda item: item.value)) or "unknown codecs"
        return False, f"{codec.value} is unavailable at {chosen}p (available: {codecs})"


def parse_metadata(payload: bytes | str) -> FormatSummary:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", errors="replace")
    data = json.loads(payload)
    formats = tuple(item for item in data.get("formats", []) if isinstance(item, dict))
    return FormatSummary(title=str(data.get("title") or "Unknown title"), formats=formats)
