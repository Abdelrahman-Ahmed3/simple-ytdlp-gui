from __future__ import annotations

import os

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .command_builder import display_command
from .errors import is_http_403
from .models import ProgressUpdate
from .progress import parse_output_path, parse_progress_line


YOUTUBE_403_CLIENT = "youtube:player_client=web_embedded"


class ProcessRunner(QObject):
    started = Signal(str)
    log_line = Signal(str)
    progress = Signal(object)
    completed = Signal(str, str)
    failed = Signal(int, str)
    cancelled = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self._buffer = ""
        self._log: list[str] = []
        self._output_path = ""
        self._cancelling = False
        self._program = ""
        self._args: list[str] = []
        self._retried_after_403 = False

    @property
    def running(self) -> bool:
        return self.process.state() != QProcess.NotRunning

    def start(self, program: str, args: list[str]) -> None:
        if self.running:
            raise RuntimeError("A process is already running")
        self._buffer = ""
        self._log.clear()
        self._output_path = ""
        self._cancelling = False
        self._program = program
        self._args = list(args)
        self._retried_after_403 = False
        self._launch(program, args)

    def _launch(self, program: str, args: list[str]) -> None:
        command = display_command(program, args)
        self.started.emit(command)
        self.process.start(program, args)

    def cancel(self) -> None:
        if not self.running:
            return
        self._cancelling = True
        self.process.terminate()
        QTimer.singleShot(1500, self._kill_tree_if_running)

    def _kill_tree_if_running(self) -> None:
        if not self.running:
            return
        pid = self.process.processId()
        if os.name == "nt" and pid:
            QProcess.startDetached("taskkill", ["/PID", str(pid), "/T", "/F"])
        else:
            self.process.kill()

    def _read_output(self) -> None:
        chunk = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._buffer += chunk.replace("\r", "\n")
        lines = self._buffer.split("\n")
        self._buffer = lines.pop()
        for line in lines:
            self._handle_line(line)

    def _handle_line(self, line: str) -> None:
        if not line:
            return
        self._log.append(line)
        self.log_line.emit(line)
        output_path = parse_output_path(line)
        if output_path:
            self._output_path = output_path
        update = parse_progress_line(line)
        if update:
            self.progress.emit(update)

    def _finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        if self._buffer.strip():
            self._handle_line(self._buffer.strip())
        self._buffer = ""
        details = "\n".join(self._log)
        if self._cancelling:
            self.cancelled.emit()
        elif exit_code == 0:
            self.progress.emit(ProgressUpdate(percent=100.0, operation="Finished"))
            self.completed.emit(self._output_path, details)
        elif is_http_403(details) and not self._retried_after_403:
            retry_args = list(self._args)
            is_youtube = any("youtube.com/" in value or "youtu.be/" in value for value in retry_args)
            if is_youtube and YOUTUBE_403_CLIENT not in retry_args:
                retry_args[0:0] = ["--extractor-args", YOUTUBE_403_CLIENT]
            if "--no-continue" not in retry_args:
                retry_args.insert(0, "--no-continue")
            if "--force-ipv4" not in retry_args:
                retry_args.insert(0, "--force-ipv4")
            if retry_args == self._args:
                self.failed.emit(exit_code, details)
                return
            self._retried_after_403 = True
            retry_message = (
                "YouTube returned HTTP 403; retrying from the beginning through its embedded client…"
                if is_youtube
                else "The server returned HTTP 403; retrying once over IPv4 from the beginning…"
            )
            self._log.append(retry_message)
            self.log_line.emit(retry_message)
            QTimer.singleShot(0, lambda: self._launch(self._program, retry_args))
        else:
            self.failed.emit(exit_code, details)

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.FailedToStart:
            self.failed.emit(-1, self.process.errorString())
