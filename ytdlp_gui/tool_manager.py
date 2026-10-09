from __future__ import annotations

import os
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QFileDevice, QObject, QProcess, QSaveFile, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .dependencies import ffmpeg_archive_target, ffmpeg_install_dir, ytdlp_download_target
from .external_process import prepare_external_process


YTDLP_RELEASE_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
FFMPEG_ARCHIVE_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_CHECKSUM_URL = FFMPEG_ARCHIVE_URL + ".sha256"
FFMPEG_RELEASE_API = "https://api.github.com/repos/GyanD/codexffmpeg/releases/latest"


def ffmpeg_asset_url(release: dict[str, object]) -> str:
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise ValueError("release assets are missing")
    for item in assets:
        if not isinstance(item, dict) or not str(item.get("name", "")).endswith("-essentials_build.zip"):
            continue
        url = str(item.get("browser_download_url", ""))
        if url.startswith("https://github.com/GyanD/codexffmpeg/releases/download/"):
            return url
        raise ValueError("unexpected release URL")
    raise ValueError("the essentials ZIP was not found")


def find_ffmpeg_members(bundle: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    wanted: dict[str, zipfile.ZipInfo] = {}
    for item in bundle.infolist():
        parts = tuple(part.lower() for part in PurePosixPath(item.filename).parts)
        if not item.is_dir() and len(parts) >= 2 and parts[-2:] in {
            ("bin", "ffmpeg.exe"),
            ("bin", "ffprobe.exe"),
        }:
            wanted[parts[-1]] = item
    missing = {"ffmpeg.exe", "ffprobe.exe"} - wanted.keys()
    if missing:
        raise ValueError(f"FFmpeg archive is missing: {', '.join(sorted(missing))}")
    return wanted


def extract_ffmpeg_binaries(archive: Path, target_dir: Path) -> Path:
    """Safely extract only ffmpeg.exe and ffprobe.exe from a Windows build archive."""
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ffmpeg-install-", dir=str(target_dir.parent)))
    try:
        with zipfile.ZipFile(archive) as bundle:
            wanted = find_ffmpeg_members(bundle)
            for filename, item in wanted.items():
                with bundle.open(item) as source, (staging / filename).open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)

        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("ffmpeg.exe", "ffprobe.exe"):
            os.replace(staging / filename, target_dir / filename)
        return target_dir / "ffmpeg.exe"
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FfmpegExtractWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, archive: Path, target_dir: Path) -> None:
        super().__init__()
        self.archive = archive
        self.target_dir = target_dir

    @Slot()
    def run(self) -> None:
        try:
            executable = extract_ffmpeg_binaries(self.archive, self.target_dir)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            self.finished.emit(False, f"Could not extract FFmpeg: {exc}")
            return
        self.finished.emit(True, str(executable))


class ToolManager(QObject):
    message = Signal(str)
    download_progress = Signal(str, int, int)
    install_finished = Signal(bool, str)
    ffmpeg_install_finished = Signal(bool, str)
    update_finished = Signal(bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.network = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._operation = ""
        self._cancelled = False
        self._ffmpeg_checksum = ""
        self._ffmpeg_archive_url = FFMPEG_ARCHIVE_URL
        self._ffmpeg_file: QSaveFile | None = None
        self._extract_thread: QThread | None = None
        self._extract_worker: FfmpegExtractWorker | None = None
        self._update_process = QProcess(self)
        self._update_process.setProcessChannelMode(QProcess.MergedChannels)
        self._update_process.readyReadStandardOutput.connect(self._update_output)
        self._update_process.finished.connect(self._update_done)
        self._update_process.errorOccurred.connect(self._update_error)
        self._update_log: list[str] = []
        self._updating = False
        self._update_timed_out = False
        self.updated_ytdlp_path = ""
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(120_000)
        self._update_timer.timeout.connect(self._update_timeout)

    @property
    def busy(self) -> bool:
        return self._reply is not None or self._extract_thread is not None or self._updating

    @property
    def can_cancel(self) -> bool:
        return self._reply is not None or self._updating

    def install_ytdlp(self) -> None:
        if self.busy:
            return
        self._operation = "ytdlp"
        self._cancelled = False
        self.message.emit("Downloading the latest yt-dlp release…")
        request = QNetworkRequest(QUrl(YTDLP_RELEASE_URL))
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        self._reply = self.network.get(request)
        self._reply.downloadProgress.connect(
            lambda received, total: self.download_progress.emit("yt-dlp", received, total)
        )
        self._reply.finished.connect(self._install_done)

    def _install_done(self) -> None:
        assert self._reply is not None
        reply = self._reply
        self._reply = None
        self._operation = ""
        if reply.error() != QNetworkReply.NoError:
            message = "yt-dlp installation was cancelled." if self._cancelled else f"Could not download yt-dlp: {reply.errorString()}"
            self.install_finished.emit(False, message)
            reply.deleteLater()
            return
        target = ytdlp_download_target()
        file = QSaveFile(str(target))
        if not file.open(QFileDevice.WriteOnly):
            self.install_finished.emit(False, f"Could not write {target}: {file.errorString()}")
            reply.deleteLater()
            return
        file.write(reply.readAll())
        if not file.commit():
            self.install_finished.emit(False, f"Could not save {target}: {file.errorString()}")
            reply.deleteLater()
            return
        if os.name != "nt":
            target.chmod(0o755)
        self.install_finished.emit(True, str(target))
        reply.deleteLater()

    def install_ffmpeg(self) -> None:
        if self.busy:
            return
        self._operation = "ffmpeg_release"
        self._cancelled = False
        self.message.emit("Locating the latest FFmpeg release…")
        request = QNetworkRequest(QUrl(FFMPEG_RELEASE_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"yt-dlp-gui")
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        self._reply = self.network.get(request)
        self._reply.finished.connect(self._ffmpeg_release_done)

    def _ffmpeg_release_done(self) -> None:
        assert self._reply is not None
        reply = self._reply
        self._reply = None
        self._ffmpeg_archive_url = FFMPEG_ARCHIVE_URL
        if self._cancelled:
            reply.deleteLater()
            self._finish_ffmpeg(False, "FFmpeg installation was cancelled.")
            return
        if reply.error() == QNetworkReply.NoError:
            try:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
                self._ffmpeg_archive_url = ffmpeg_asset_url(data)
            except (TypeError, ValueError, json.JSONDecodeError):
                self.message.emit("GitHub mirror lookup failed; using the direct FFmpeg provider…")
        else:
            self.message.emit("GitHub mirror is unavailable; using the direct FFmpeg provider…")
        reply.deleteLater()
        self._start_ffmpeg_checksum_download()

    def _start_ffmpeg_checksum_download(self) -> None:
        self._operation = "ffmpeg_checksum"
        self.message.emit("Checking the FFmpeg package checksum…")
        request = QNetworkRequest(QUrl(FFMPEG_CHECKSUM_URL))
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        self._reply = self.network.get(request)
        self._reply.finished.connect(self._ffmpeg_checksum_done)

    def _ffmpeg_checksum_done(self) -> None:
        assert self._reply is not None
        reply = self._reply
        self._reply = None
        if reply.error() != QNetworkReply.NoError:
            message = "FFmpeg installation was cancelled." if self._cancelled else f"Could not download the FFmpeg checksum: {reply.errorString()}"
            self._finish_ffmpeg(False, message)
            reply.deleteLater()
            return
        text = bytes(reply.readAll()).decode("ascii", errors="replace")
        reply.deleteLater()
        match = re.search(r"\b([0-9a-fA-F]{64})\b", text)
        if not match:
            self._finish_ffmpeg(False, "The FFmpeg provider returned an invalid checksum file.")
            return
        self._ffmpeg_checksum = match.group(1).lower()
        self._start_ffmpeg_archive_download()

    def _start_ffmpeg_archive_download(self) -> None:
        archive = ffmpeg_archive_target()
        self._ffmpeg_file = QSaveFile(str(archive))
        if not self._ffmpeg_file.open(QFileDevice.WriteOnly):
            self._finish_ffmpeg(False, f"Could not create the FFmpeg archive: {self._ffmpeg_file.errorString()}")
            self._ffmpeg_file = None
            return
        self._operation = "ffmpeg_archive"
        self.message.emit("Downloading FFmpeg…")
        request = QNetworkRequest(QUrl(self._ffmpeg_archive_url))
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)
        self._reply = self.network.get(request)
        self._reply.readyRead.connect(self._write_ffmpeg_chunk)
        self._reply.downloadProgress.connect(
            lambda received, total: self.download_progress.emit("FFmpeg", received, total)
        )
        self._reply.finished.connect(self._ffmpeg_archive_done)

    def _write_ffmpeg_chunk(self) -> None:
        if self._reply is not None and self._ffmpeg_file is not None:
            self._ffmpeg_file.write(self._reply.readAll())

    def _ffmpeg_archive_done(self) -> None:
        assert self._reply is not None
        reply = self._reply
        self._write_ffmpeg_chunk()
        self._reply = None
        if reply.error() != QNetworkReply.NoError:
            if self._ffmpeg_file is not None:
                self._ffmpeg_file.cancelWriting()
            self._ffmpeg_file = None
            message = "FFmpeg installation was cancelled." if self._cancelled else f"Could not download FFmpeg: {reply.errorString()}"
            self._finish_ffmpeg(False, message)
            reply.deleteLater()
            return
        reply.deleteLater()
        if self._ffmpeg_file is None or not self._ffmpeg_file.commit():
            error = self._ffmpeg_file.errorString() if self._ffmpeg_file is not None else "unknown write error"
            self._ffmpeg_file = None
            self._finish_ffmpeg(False, f"Could not save the FFmpeg archive: {error}")
            return
        self._ffmpeg_file = None
        archive = ffmpeg_archive_target()
        self.message.emit("Verifying the FFmpeg download…")
        digest = sha256_file(archive)
        if digest.lower() != self._ffmpeg_checksum:
            archive.unlink(missing_ok=True)
            self._finish_ffmpeg(False, "The downloaded FFmpeg archive failed SHA-256 verification and was deleted.")
            return
        self._start_ffmpeg_extraction(archive)

    def _start_ffmpeg_extraction(self, archive: Path) -> None:
        self._operation = "ffmpeg_extract"
        self.message.emit("Extracting FFmpeg…")
        self._extract_thread = QThread(self)
        self._extract_worker = FfmpegExtractWorker(archive, ffmpeg_install_dir())
        self._extract_worker.moveToThread(self._extract_thread)
        self._extract_thread.started.connect(self._extract_worker.run)
        self._extract_worker.finished.connect(self._ffmpeg_extracted)
        self._extract_worker.finished.connect(self._extract_thread.quit)
        self._extract_worker.finished.connect(self._extract_worker.deleteLater)
        self._extract_thread.finished.connect(self._extraction_thread_finished)
        self._extract_thread.finished.connect(self._extract_thread.deleteLater)
        self._extract_thread.start()

    def _ffmpeg_extracted(self, success: bool, message: str) -> None:
        ffmpeg_archive_target().unlink(missing_ok=True)
        self._finish_ffmpeg(success, message)

    def _extraction_thread_finished(self) -> None:
        self._extract_thread = None
        self._extract_worker = None

    def _finish_ffmpeg(self, success: bool, message: str) -> None:
        self._operation = ""
        self.ffmpeg_install_finished.emit(success, message)

    def cancel_install(self) -> None:
        if self._updating:
            self._cancelled = True
            self._update_process.kill()
            return
        if self._reply is None:
            return
        self._cancelled = True
        self._reply.abort()

    def update_ytdlp(self, executable: str) -> None:
        if self.busy:
            return
        self._updating = True
        self._cancelled = False
        self._update_timed_out = False
        self.updated_ytdlp_path = ""
        self._update_log.clear()
        try:
            target = ytdlp_download_target()
            if Path(executable).resolve() != target.resolve():
                # Never attempt to overwrite a WinGet / Program Files install.
                file = QSaveFile(str(target))
                if not file.open(QFileDevice.WriteOnly):
                    raise OSError(file.errorString())
                with Path(executable).open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        if file.write(chunk) != len(chunk):
                            file.cancelWriting()
                            raise OSError(file.errorString())
                if not file.commit():
                    raise OSError(file.errorString())
                if os.name != "nt":
                    target.chmod(0o755)
            self.updated_ytdlp_path = str(target)
            prepare_external_process(self._update_process)
        except OSError as exc:
            self._finish_update(False, f"Could not prepare the app's yt-dlp copy: {exc}")
            return
        self.message.emit("Checking for yt-dlp updates…")
        self._update_process.start(str(target), ["--ignore-config", "--socket-timeout", "15", "-U"])
        self._update_timer.start()

    def _update_output(self) -> None:
        text = bytes(self._update_process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._update_log.append(text)
        if "Updating to " in text:
            self.message.emit("Installing the yt-dlp update…")

    def _update_done(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        if not self._updating:
            return
        self._update_output()
        details = "".join(self._update_log).strip()
        if self._cancelled:
            self._finish_update(False, "yt-dlp update cancelled. The previous version is still available.")
        elif self._update_timed_out:
            self._finish_update(False, "yt-dlp update timed out. Check your connection or try Tools → Check for yt-dlp updates.")
        else:
            self._finish_update(exit_code == 0, details or f"yt-dlp exited with code {exit_code}")

    def _update_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            self._finish_update(False, f"Could not start the yt-dlp updater: {self._update_process.errorString()}")

    def _update_timeout(self) -> None:
        if self._updating:
            self._update_timed_out = True
            self._update_process.kill()

    def _finish_update(self, success: bool, details: str) -> None:
        if not self._updating:
            return
        self._update_timer.stop()
        self._updating = False
        self.update_finished.emit(success, details)
