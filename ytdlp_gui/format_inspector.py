from __future__ import annotations

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .command_builder import build_metadata_args
from .formats import FormatSummary, parse_metadata
from .external_process import prepare_external_process


class FormatInspector(QObject):
    INACTIVITY_TIMEOUT_MS = 60_000

    started = Signal()
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    log_line = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._cancelling = False
        self._timed_out = False
        self._failure_emitted = False
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.setInterval(self.INACTIVITY_TIMEOUT_MS)
        self._timeout.timeout.connect(self._on_timeout)
        self.process.readyReadStandardOutput.connect(self._read_stdout)
        self.process.readyReadStandardError.connect(self._read_stderr)

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.NotRunning

    def inspect(self, program: str, url: str) -> None:
        if self.running:
            self.cancel()
            self.process.waitForFinished(1000)
        self._stdout.clear()
        self._stderr.clear()
        self._cancelling = False
        self._timed_out = False
        self._failure_emitted = False
        self.started.emit()
        prepare_external_process(self.process)
        self.process.start(program, build_metadata_args(url))
        self._timeout.start()

    def cancel(self) -> None:
        if not self.running:
            return
        self._cancelling = True
        self._timeout.stop()
        self.process.kill()

    def _read_stdout(self) -> None:
        data = bytes(self.process.readAllStandardOutput())
        self._stdout.extend(data)
        if data and not self._cancelling:
            self._timeout.start()

    def _read_stderr(self) -> None:
        data = bytes(self.process.readAllStandardError())
        self._stderr.extend(data)
        if data and not self._cancelling:
            self._timeout.start()
        for line in data.decode("utf-8", errors="replace").splitlines():
            self.log_line.emit(line)

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self._timeout.stop()
        self._read_stdout()
        self._read_stderr()
        if self._cancelling:
            self._cancelling = False
            self.cancelled.emit()
            return
        if self._timed_out:
            details = self._stderr.decode("utf-8", errors="replace").strip()
            self._emit_failure(
                "yt-dlp stopped responding for 60 seconds while fetching information."
                + (f"\n\n{details}" if details else "")
            )
            return
        if exit_code != 0:
            message = self._stderr.decode("utf-8", errors="replace").strip()
            self._emit_failure(message or f"yt-dlp exited with code {exit_code}")
            return
        try:
            summary: FormatSummary = parse_metadata(bytes(self._stdout))
        except (ValueError, TypeError) as exc:
            self._emit_failure(f"Could not read yt-dlp format data: {exc}")
            return
        self.completed.emit(summary)

    def _on_timeout(self) -> None:
        if not self.running:
            return
        self._timed_out = True
        self.log_line.emit("No yt-dlp output for 60 seconds; cancelling the format check.")
        self.process.kill()

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart and not self._cancelling:
            self._timeout.stop()
            self._emit_failure(f"Could not start yt-dlp: {self.process.errorString()}")

    def _emit_failure(self, message: str) -> None:
        if self._failure_emitted:
            return
        self._failure_emitted = True
        self.failed.emit(message)
