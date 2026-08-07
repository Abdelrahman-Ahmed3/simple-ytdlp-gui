from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


class AppSettings:
    def __init__(self) -> None:
        self._settings = QSettings("OpenUtility", "yt-dlp GUI")

    @property
    def output_folder(self) -> str:
        default = QStandardPaths.writableLocation(QStandardPaths.DownloadLocation)
        return self._settings.value("output/folder", default, type=str)

    @output_folder.setter
    def output_folder(self, value: str) -> None:
        self._settings.setValue("output/folder", value)

    def get(self, key: str, default: str = "") -> str:
        return self._settings.value(key, default, type=str)

    def set(self, key: str, value: str | bool) -> None:
        self._settings.setValue(key, value)

    def get_bool(self, key: str, default: bool = False) -> bool:
        return self._settings.value(key, default, type=bool)

    def sync(self) -> None:
        self._settings.sync()

    @staticmethod
    def ensure_output_folder(path: str) -> Path:
        folder = Path(path).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        return folder
