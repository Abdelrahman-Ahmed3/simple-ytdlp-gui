import json

from ytdlp_gui.formats import parse_metadata
from ytdlp_gui.models import VideoCodec


def summary():
    return parse_metadata(
        json.dumps(
            {
                "title": "Test video",
                "formats": [
                    {"format_id": "1", "height": 1080, "vcodec": "avc1.640028"},
                    {"format_id": "2", "height": 1080, "vcodec": "vp9"},
                    {"format_id": "3", "height": 1440, "vcodec": "vp09.00.50.08"},
                    {"format_id": "4", "height": 1440, "vcodec": "av01.0.12M.08"},
                    {"format_id": "5", "height": 720, "vcodec": "avc1.4d401f"},
                    {"format_id": "a", "vcodec": "none", "acodec": "mp4a.40.2"},
                ],
            }
        )
    )


def test_metadata_reports_heights_and_codecs() -> None:
    data = summary()
    assert data.video_heights == (1440, 1080, 720)
    assert data.codecs_at(1440) == {VideoCodec.VP9, VideoCodec.AV1}


def test_unavailable_codec_at_exact_quality_is_clear() -> None:
    supported, message = summary().supports("1440p", VideoCodec.H264)
    assert supported is False
    assert "unavailable at 1440p" in message
    assert "AV1" in message and "VP9" in message


def test_lower_resolution_fallback_is_reported() -> None:
    supported, message = summary().supports("2160p", VideoCodec.H264, fallback_lower=True)
    assert supported is True
    assert "1080p" in message


def test_auto_can_fall_back_to_closest_lower() -> None:
    supported, message = summary().supports("2160p", VideoCodec.AUTO, fallback_lower=True)
    assert supported is True
    assert "1440p" in message
