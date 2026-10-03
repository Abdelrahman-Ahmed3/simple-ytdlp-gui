from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class DownloadMode(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"


class VideoCodec(str, Enum):
    AUTO = "Auto"
    H264 = "H.264 / AVC"
    VP9 = "VP9"
    AV1 = "AV1"


class Container(str, Enum):
    AUTO = "Auto"
    MP4 = "MP4"
    MKV = "MKV"
    WEBM = "WebM"


@dataclass(frozen=True)
class DownloadOptions:
    url: str
    output_dir: Path
    mode: DownloadMode = DownloadMode.VIDEO
    quality: str = "Best"
    codec: VideoCodec = VideoCodec.AUTO
    container: Container = Container.AUTO
    fallback_lower: bool = False
    audio_format: str = "Best"
    audio_bitrate: str = "Best/default"
    ffmpeg_path: str = ""
    section_start: float | None = None
    section_end: float | None = None
    precise_cuts: bool = False


@dataclass(frozen=True)
class ProgressUpdate:
    percent: float | None = None
    speed: str = ""
    downloaded: int | None = None
    total: int | None = None
    eta: str = ""
    operation: str = ""
