from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import QStandardPaths


def app_tools_dir() -> Path:
    root = QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)
    return Path(root) / "tools"


def resolve_executable(configured: str, names: tuple[str, ...], local_names: tuple[str, ...]) -> str:
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path)
        if path.is_dir():
            for name in names:
                candidate = path / name
                if candidate.is_file():
                    return str(candidate)

    candidates = [Path.cwd() / "tools", app_tools_dir()]
    for folder in candidates:
        for name in local_names:
            candidate = folder / name
            if candidate.is_file():
                return str(candidate)

    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return ""


def find_ytdlp(configured: str = "") -> str:
    return resolve_executable(configured, ("yt-dlp.exe", "yt-dlp"), ("yt-dlp.exe", "yt-dlp"))


def find_ffmpeg(configured: str = "") -> str:
    return resolve_executable(
        configured,
        ("ffmpeg.exe", "ffmpeg"),
        (str(Path("ffmpeg") / "ffmpeg.exe"), "ffmpeg.exe", "ffmpeg"),
    )


def ffmpeg_location_arg(executable: str) -> str:
    if not executable:
        return ""
    path = Path(executable)
    return str(path.parent if path.is_file() else path)


def ytdlp_download_target() -> Path:
    folder = app_tools_dir()
    folder.mkdir(parents=True, exist_ok=True)
    return folder / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")


def ffmpeg_install_dir() -> Path:
    folder = app_tools_dir() / "ffmpeg"
    folder.parent.mkdir(parents=True, exist_ok=True)
    return folder


def ffmpeg_archive_target() -> Path:
    folder = app_tools_dir() / "downloads"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / "ffmpeg-release-essentials.zip"
