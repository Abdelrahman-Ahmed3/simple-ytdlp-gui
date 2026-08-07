import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from ytdlp_gui.tool_manager import ffmpeg_asset_url, find_ffmpeg_members, sha256_file


def archive_bytes(include_ffprobe: bool = True) -> io.BytesIO:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as bundle:
        bundle.writestr("ffmpeg-release-essentials/bin/ffmpeg.exe", b"ffmpeg-binary")
        if include_ffprobe:
            bundle.writestr("ffmpeg-release-essentials/bin/ffprobe.exe", b"ffprobe-binary")
        bundle.writestr("ffmpeg-release-essentials/doc/readme.txt", b"not extracted")
    payload.seek(0)
    return payload


def test_ffmpeg_archive_selects_only_required_binaries() -> None:
    with zipfile.ZipFile(archive_bytes()) as bundle:
        members = find_ffmpeg_members(bundle)
        assert set(members) == {"ffmpeg.exe", "ffprobe.exe"}
        assert bundle.read(members["ffmpeg.exe"]) == b"ffmpeg-binary"


def test_ffmpeg_archive_must_contain_ffprobe() -> None:
    with zipfile.ZipFile(archive_bytes(include_ffprobe=False)) as bundle:
        with pytest.raises(ValueError, match="ffprobe.exe"):
            find_ffmpeg_members(bundle)


def test_sha256_file_streams_the_expected_digest() -> None:
    file = Path(__file__)
    expected = hashlib.sha256(file.read_bytes()).hexdigest()
    assert sha256_file(file) == expected


def test_ffmpeg_release_selects_the_essentials_zip() -> None:
    url = "https://github.com/GyanD/codexffmpeg/releases/download/9.0/ffmpeg-9.0-essentials_build.zip"
    release = {
        "assets": [
            {"name": "ffmpeg-9.0-full_build.zip", "browser_download_url": "https://example.com/full.zip"},
            {"name": "ffmpeg-9.0-essentials_build.zip", "browser_download_url": url},
        ]
    }
    assert ffmpeg_asset_url(release) == url


def test_ffmpeg_release_rejects_untrusted_asset_host() -> None:
    release = {
        "assets": [
            {"name": "ffmpeg-9.0-essentials_build.zip", "browser_download_url": "https://example.com/ffmpeg.zip"}
        ]
    }
    with pytest.raises(ValueError, match="unexpected release URL"):
        ffmpeg_asset_url(release)
