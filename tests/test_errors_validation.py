from pathlib import Path

from ytdlp_gui.errors import friendly_error
from ytdlp_gui.validation import validate_output_folder, validate_url


def test_url_validation() -> None:
    assert validate_url("")
    assert validate_url("not a url")
    assert validate_url("ftp://example.com/video")
    assert validate_url("https://example.com/video") is None


def test_output_folder_rejects_files() -> None:
    assert validate_output_folder(str(Path(__file__)))


def test_common_error_messages_keep_specific_meaning() -> None:
    assert "quality" in friendly_error("ERROR: Requested format is not available", 1)
    assert "FFmpeg" in friendly_error("ERROR: ffmpeg not found", 1)
    assert "authentication" in friendly_error("ERROR: Login required; use cookies", 1)
