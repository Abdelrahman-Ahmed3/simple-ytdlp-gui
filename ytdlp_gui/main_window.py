from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .command_builder import build_download_args, display_command
from .dependencies import find_ffmpeg, find_ytdlp
from .dialogs import ErrorDialog, LogDialog, SettingsDialog, information
from .errors import friendly_error
from .format_inspector import FormatInspector
from .formats import FormatSummary
from .models import Container, DownloadMode, DownloadOptions, ProgressUpdate, VideoCodec
from .process_runner import ProcessRunner
from .progress import format_eta, human_bytes
from .settings import AppSettings
from .tool_manager import ToolManager
from .validation import parse_section, validate_output_folder, validate_url


QUALITIES = ("Best", "2160p", "1440p", "1080p", "720p", "480p", "360p")
AUDIO_FORMATS = ("Best", "MP3", "M4A", "Opus", "FLAC", "WAV")
AUDIO_BITRATES = ("Best/default", "320 kbps", "256 kbps", "192 kbps", "128 kbps")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("yt-dlp GUI")
        self.setMinimumWidth(660)
        self.settings = AppSettings()
        self.runner = ProcessRunner(self)
        self.inspector = FormatInspector(self)
        self.tools = ToolManager(self)
        self.log_dialog = LogDialog(self)
        self.format_summary: FormatSummary | None = None
        self._close_after_cancel = False
        self._pending_action = ""
        self._tool_installing = ""
        self._activity_context = ""
        self._activity_phase = ""
        self._activity_elapsed = QElapsedTimer()
        self._activity_timer = QTimer(self)
        self._activity_timer.setInterval(1000)
        self._activity_timer.timeout.connect(self._refresh_activity)
        self._build_ui()
        self._restore_settings()
        self._connect_signals()
        self._refresh_dependencies()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        url_row = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste a supported video URL")
        self.paste_button = QPushButton("Paste")
        self.inspect_button = QPushButton("Check formats")
        url_row.addWidget(self.url_edit, 1)
        url_row.addWidget(self.paste_button)
        url_row.addWidget(self.inspect_button)
        root.addWidget(QLabel("URL:"))
        root.addLayout(url_row)

        mode_row = QHBoxLayout()
        self.video_radio = QRadioButton("Video")
        self.audio_radio = QRadioButton("Audio only")
        self.video_radio.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.video_radio)
        mode_group.addButton(self.audio_radio)
        mode_row.addWidget(self.video_radio)
        mode_row.addWidget(self.audio_radio)
        mode_row.addStretch()
        root.addLayout(mode_row)

        self.options_frame = QFrame()
        self.options_frame.setFrameShape(QFrame.StyledPanel)
        options_layout = QVBoxLayout(self.options_frame)

        self.video_widget = QWidget()
        video_form = QFormLayout(self.video_widget)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(QUALITIES)
        self.codec_combo = QComboBox()
        self.codec_combo.addItems([item.value for item in VideoCodec])
        self.container_combo = QComboBox()
        self.container_combo.addItems([item.value for item in Container])
        self.fallback_check = QCheckBox("Allow closest lower resolution")
        video_form.addRow("Quality:", self.quality_combo)
        video_form.addRow("Source video codec:", self.codec_combo)
        video_form.addRow("Container:", self.container_combo)
        video_form.addRow("", self.fallback_check)
        options_layout.addWidget(self.video_widget)

        self.audio_widget = QWidget()
        audio_form = QFormLayout(self.audio_widget)
        self.audio_format_combo = QComboBox()
        self.audio_format_combo.addItems(AUDIO_FORMATS)
        self.audio_bitrate_combo = QComboBox()
        self.audio_bitrate_combo.addItems(AUDIO_BITRATES)
        audio_form.addRow("Audio format:", self.audio_format_combo)
        audio_form.addRow("Conversion bitrate:", self.audio_bitrate_combo)
        self.audio_widget.hide()
        options_layout.addWidget(self.audio_widget)

        self.section_check = QCheckBox("Download only a section")
        options_layout.addWidget(self.section_check)
        self.section_widget = QWidget()
        section_layout = QVBoxLayout(self.section_widget)
        section_layout.setContentsMargins(0, 0, 0, 0)
        range_row = QHBoxLayout()
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("Beginning (0:00)")
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("End of video")
        range_row.addWidget(QLabel("Start:"))
        range_row.addWidget(self.start_edit)
        range_row.addWidget(QLabel("End:"))
        range_row.addWidget(self.end_edit)
        section_layout.addLayout(range_row)
        section_help = QLabel("Use seconds, MM:SS, or HH:MM:SS. Leave one time blank to use the beginning or end.")
        section_help.setWordWrap(True)
        section_layout.addWidget(section_help)
        self.precise_cuts_check = QCheckBox("Precise video cuts (slower; re-encodes video)")
        self.precise_cuts_check.setToolTip("Without this option, video cuts may align with nearby keyframes.")
        section_layout.addWidget(self.precise_cuts_check)
        self.section_widget.setEnabled(False)
        options_layout.addWidget(self.section_widget)
        root.addWidget(self.options_frame)

        self.availability_label = QLabel("Use Check formats to inspect available streams before downloading.")
        self.availability_label.setWordWrap(True)
        root.addWidget(self.availability_label)

        root.addWidget(QLabel("Save to:"))
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.browse_button = QPushButton("Browse…")
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.browse_button)
        root.addLayout(output_row)

        self.download_button = QPushButton("DOWNLOAD")
        self.download_button.setMinimumHeight(44)
        self.download_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        root.addWidget(self.download_button)

        self.status_label = QLabel("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.details_label = QLabel("")
        self.details_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.eta_label = QLabel("ETA: —")
        self.eta_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.eta_label.setMinimumWidth(130)
        root.addWidget(self.status_label)
        root.addWidget(self.progress_bar)
        metrics_row = QHBoxLayout()
        metrics_row.addWidget(self.details_label, 1)
        metrics_row.addWidget(self.eta_label)
        root.addLayout(metrics_row)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        root.addWidget(self.cancel_button, alignment=Qt.AlignRight)

        self._build_menu()
        self.statusBar().showMessage("Ready")

    def _build_menu(self) -> None:
        tools_menu = self.menuBar().addMenu("Tools")
        self.settings_action = QAction("Settings…", self)
        self.logs_action = QAction("Debug log…", self)
        self.update_action = QAction("Check for yt-dlp updates", self)
        self.install_action = QAction("Install yt-dlp", self)
        self.install_ffmpeg_action = QAction("Install FFmpeg", self)
        tools_menu.addAction(self.settings_action)
        tools_menu.addAction(self.logs_action)
        tools_menu.addSeparator()
        tools_menu.addAction(self.update_action)
        tools_menu.addAction(self.install_action)
        tools_menu.addAction(self.install_ffmpeg_action)

    def _connect_signals(self) -> None:
        self.paste_button.clicked.connect(self._paste)
        self.inspect_button.clicked.connect(self._inspect_formats)
        self.url_edit.editingFinished.connect(self._maybe_inspect)
        self.browse_button.clicked.connect(self._browse_output)
        self.video_radio.toggled.connect(self._mode_changed)
        self.download_button.clicked.connect(self._start_download)
        self.cancel_button.clicked.connect(self._cancel_current)
        self.quality_combo.currentTextChanged.connect(self._selection_changed)
        self.codec_combo.currentTextChanged.connect(self._selection_changed)
        self.fallback_check.toggled.connect(self._selection_changed)
        self.audio_format_combo.currentTextChanged.connect(self._update_bitrate_enabled)
        self.section_check.toggled.connect(self.section_widget.setEnabled)
        self.settings_action.triggered.connect(self._show_settings)
        self.logs_action.triggered.connect(self.log_dialog.show)
        self.update_action.triggered.connect(self._update_ytdlp)
        self.install_action.triggered.connect(lambda: self._install_ytdlp(""))
        self.install_ffmpeg_action.triggered.connect(lambda: self._request_ffmpeg_install(""))

        self.runner.started.connect(lambda command: self._log(f"$ {command}"))
        self.runner.log_line.connect(self._runner_activity)
        self.runner.log_line.connect(self._log)
        self.runner.progress.connect(self._show_progress)
        self.runner.completed.connect(self._download_completed)
        self.runner.failed.connect(self._download_failed)
        self.runner.cancelled.connect(self._download_cancelled)

        self.inspector.started.connect(self._inspection_started)
        self.inspector.completed.connect(self._inspection_completed)
        self.inspector.failed.connect(self._inspection_failed)
        self.inspector.cancelled.connect(self._inspection_cancelled)
        self.inspector.log_line.connect(self._inspection_activity)
        self.inspector.log_line.connect(self._log)

        self.tools.message.connect(self._tool_message)
        self.tools.download_progress.connect(self._tool_download_progress)
        self.tools.install_finished.connect(self._install_finished)
        self.tools.ffmpeg_install_finished.connect(self._ffmpeg_install_finished)
        self.tools.update_finished.connect(self._update_finished)

    def _restore_settings(self) -> None:
        self.output_edit.setText(self.settings.output_folder)
        self._set_combo(self.quality_combo, self.settings.get("download/quality", "1080p"))
        self._set_combo(self.codec_combo, self.settings.get("download/codec", VideoCodec.H264.value))
        self._set_combo(self.container_combo, self.settings.get("download/container", Container.MP4.value))
        self._set_combo(self.audio_format_combo, self.settings.get("download/audio_format", "M4A"))
        self._set_combo(self.audio_bitrate_combo, self.settings.get("download/audio_bitrate", "Best/default"))
        self.fallback_check.setChecked(self.settings.get_bool("download/fallback_lower", False))
        self.section_check.setChecked(self.settings.get_bool("download/section", False))
        self.section_widget.setEnabled(self.section_check.isChecked())
        self.start_edit.setText(self.settings.get("download/section_start"))
        self.end_edit.setText(self.settings.get("download/section_end"))
        self.precise_cuts_check.setChecked(self.settings.get_bool("download/precise_cuts", False))

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _save_settings(self) -> None:
        self.settings.output_folder = self.output_edit.text().strip()
        self.settings.set("download/quality", self.quality_combo.currentText())
        self.settings.set("download/codec", self.codec_combo.currentText())
        self.settings.set("download/container", self.container_combo.currentText())
        self.settings.set("download/audio_format", self.audio_format_combo.currentText())
        self.settings.set("download/audio_bitrate", self.audio_bitrate_combo.currentText())
        self.settings.set("download/fallback_lower", self.fallback_check.isChecked())
        self.settings.set("download/section", self.section_check.isChecked())
        self.settings.set("download/section_start", self.start_edit.text().strip())
        self.settings.set("download/section_end", self.end_edit.text().strip())
        self.settings.set("download/precise_cuts", self.precise_cuts_check.isChecked())
        self.settings.sync()

    def _refresh_dependencies(self) -> None:
        self.ytdlp_path = find_ytdlp(self.settings.get("tools/ytdlp"))
        self.ffmpeg_path = find_ffmpeg(self.settings.get("tools/ffmpeg"))
        self.install_action.setVisible(not bool(self.ytdlp_path))
        self.install_ffmpeg_action.setVisible(not bool(self.ffmpeg_path))
        self.update_action.setEnabled(bool(self.ytdlp_path))
        if not self.ytdlp_path:
            self.statusBar().showMessage("yt-dlp was not found. Use Tools → Install yt-dlp or configure its path.")

    def _paste(self) -> None:
        self.url_edit.setText(QGuiApplication.clipboard().text().strip())
        self._maybe_inspect()

    def _maybe_inspect(self) -> None:
        if validate_url(self.url_edit.text()) is None and self.ytdlp_path and not self.runner.running:
            self._inspect_formats()

    def _inspect_formats(self) -> None:
        if self.inspector.running:
            self.inspector.cancel()
            return
        error = validate_url(self.url_edit.text())
        if error:
            self._warn(error)
            return
        if not self.ytdlp_path:
            self._missing_ytdlp("inspect")
            return
        self.format_summary = None
        self.inspector.inspect(self.ytdlp_path, self.url_edit.text().strip())

    def _inspection_started(self) -> None:
        self.inspect_button.setEnabled(True)
        self.inspect_button.setText("Cancel check")
        self.availability_label.setText(
            "Contacting the site through yt-dlp. Some sites can take 30–60 seconds to return formats."
        )
        self._begin_activity("inspection", "Opening the URL")

    def _inspection_completed(self, summary: FormatSummary) -> None:
        self._end_activity("inspection")
        self.eta_label.setText("ETA: —")
        self.format_summary = summary
        self.inspect_button.setEnabled(True)
        self.inspect_button.setText("Check formats")
        self.status_label.setText("Ready")
        self._log(f"Metadata: {summary.title}; video heights: {summary.video_heights}")
        self._selection_changed()

    def _inspection_failed(self, details: str) -> None:
        self._end_activity("inspection")
        self.eta_label.setText("ETA: —")
        self.inspect_button.setEnabled(True)
        self.inspect_button.setText("Check formats")
        self.status_label.setText("Could not fetch information")
        if details.startswith("yt-dlp stopped responding"):
            message = "yt-dlp stopped responding. Check the URL or connection and try again."
        else:
            message = friendly_error(details, 1)
        self.availability_label.setText(f"Format check failed: {message}")
        self._log(details)

    def _inspection_cancelled(self) -> None:
        if self._activity_context == "inspection":
            self._end_activity("inspection")
            self.status_label.setText("Format check cancelled")
            self.details_label.clear()
            self.eta_label.setText("ETA: —")
        self.inspect_button.setText("Check formats")
        self.inspect_button.setEnabled(not self.runner.running)

    def _inspection_activity(self, line: str) -> None:
        if self._activity_context != "inspection":
            return
        phase = self._activity_phase_from_log(line)
        if phase:
            self._activity_phase = phase
            self._refresh_activity()

    def _selection_changed(self, *_args: object) -> None:
        if not self.format_summary or not self.video_radio.isChecked():
            return
        supported, message = self.format_summary.supports(
            self.quality_combo.currentText(),
            VideoCodec(self.codec_combo.currentText()),
            self.fallback_check.isChecked(),
        )
        prefix = "✓" if supported else "⚠"
        self.availability_label.setText(f"{prefix} {self.format_summary.title} — {message}")
        self.availability_label.setStyleSheet("" if supported else "color: #a35a00")

    def _mode_changed(self, video: bool) -> None:
        self.precise_cuts_check.setVisible(video)
        self.video_widget.setVisible(video)
        self.audio_widget.setVisible(not video)
        if video:
            self._selection_changed()
        else:
            self.availability_label.setText("Audio-only mode uses the best available audio source.")
            self.availability_label.setStyleSheet("")
        self._update_bitrate_enabled()

    def _update_bitrate_enabled(self, *_args: object) -> None:
        self.audio_bitrate_combo.setEnabled(self.audio_format_combo.currentText().lower() in {"mp3", "m4a", "opus"})

    def _browse_output(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def _options(self) -> DownloadOptions:
        start, end = parse_section(self.start_edit.text(), self.end_edit.text()) if self.section_check.isChecked() else (None, None)
        return DownloadOptions(
            url=self.url_edit.text().strip(),
            output_dir=Path(self.output_edit.text().strip()).expanduser(),
            mode=DownloadMode.VIDEO if self.video_radio.isChecked() else DownloadMode.AUDIO,
            quality=self.quality_combo.currentText(),
            codec=VideoCodec(self.codec_combo.currentText()),
            container=Container(self.container_combo.currentText()),
            fallback_lower=self.fallback_check.isChecked(),
            audio_format=self.audio_format_combo.currentText(),
            audio_bitrate=self.audio_bitrate_combo.currentText(),
            ffmpeg_path=self.ffmpeg_path,
            section_start=start,
            section_end=end,
            precise_cuts=self.precise_cuts_check.isChecked(),
        )

    def _requires_ffmpeg(self, options: DownloadOptions) -> bool:
        if options.section_start is not None or options.section_end is not None:
            return True
        if options.mode is DownloadMode.VIDEO:
            return True
        return options.audio_format != "Best"

    def _start_download(self) -> None:
        error = validate_url(self.url_edit.text()) or validate_output_folder(self.output_edit.text())
        if error:
            self._warn(error)
            return
        try:
            options = self._options()
        except ValueError as exc:
            self._warn(str(exc))
            return
        if not self.ytdlp_path:
            self._missing_ytdlp("download")
            return
        if options.mode is DownloadMode.VIDEO and options.container is Container.WEBM and options.codec is VideoCodec.H264:
            self._warn("H.264 video is not compatible with the WebM container. Choose Auto, MKV, or MP4, or select a WebM-compatible codec.")
            return
        if self._requires_ffmpeg(options) and not self.ffmpeg_path:
            self._request_ffmpeg_install("download")
            return
        try:
            options.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._warn(f"Could not create the output folder: {exc}")
            return
        if self.format_summary and options.mode is DownloadMode.VIDEO:
            supported, message = self.format_summary.supports(options.quality, options.codec, options.fallback_lower)
            if not supported:
                self._warn(message + ". Choose another combination or enable the lower-resolution fallback.")
                return
        if self.inspector.running:
            self.inspector.cancel()
        self._save_settings()
        self._set_running(True)
        self._begin_activity("download", "Starting yt-dlp")
        self.runner.start(self.ytdlp_path, build_download_args(options))

    def _set_running(self, running: bool) -> None:
        self.download_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.inspect_button.setEnabled(not running and not self.inspector.running)
        self.options_frame.setEnabled(not running)
        self.url_edit.setEnabled(not running)

    def _cancel_current(self) -> None:
        if self.runner.running:
            self.runner.cancel()
        elif self.tools.busy and self.tools.can_cancel:
            self.tools.cancel_install()

    def _show_progress(self, update: ProgressUpdate) -> None:
        self._end_activity("download")
        operation = update.operation or self.status_label.text()
        if operation == "Downloading":
            operation = "Downloading video" if self.video_radio.isChecked() else "Downloading audio"
        if update.operation == "Downloading video" and self.audio_radio.isChecked():
            operation = "Downloading audio"
        self.status_label.setText(operation)
        if update.percent is not None:
            percent = max(0.0, min(100.0, update.percent))
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(round(percent * 10))
            self.progress_bar.setFormat(f"{percent:.1f}%")
        elif operation.startswith("Downloading") or operation in {"Merging", "Converting audio", "Converting video"}:
            self.progress_bar.setRange(0, 0)
        parts: list[str] = []
        if update.speed:
            parts.append(update.speed)
        if update.downloaded is not None:
            size = human_bytes(update.downloaded)
            if update.total is not None:
                size += f" / {human_bytes(update.total)}"
            parts.append(size)
        if parts:
            self.details_label.setText(" | ".join(parts))
        if update.eta:
            self.eta_label.setText(f"ETA: {format_eta(update.eta)}")
        elif update.percent is not None and update.percent >= 100:
            self.eta_label.setText("ETA: 00:00")
        elif operation in {"Merging", "Converting audio", "Converting video"}:
            self.eta_label.setText("ETA: finalizing…")
        else:
            self.eta_label.setText("ETA: calculating…")

    def _runner_activity(self, line: str) -> None:
        if self._activity_context != "download":
            return
        phase = self._activity_phase_from_log(line)
        if phase:
            self._activity_phase = phase
            self._refresh_activity()

    @staticmethod
    def _activity_phase_from_log(line: str) -> str:
        lowered = line.lower()
        if "extracting url" in lowered:
            return "Opening the URL"
        if "downloading webpage" in lowered:
            return "Loading the webpage"
        if "player api json" in lowered:
            return "Contacting the site's player API"
        if "m3u8 information" in lowered:
            return "Reading the stream playlist"
        if "mpd manifest" in lowered:
            return "Reading the stream manifest"
        if "available formats" in lowered:
            return "Reading available formats"
        return ""

    def _begin_activity(self, context: str, phase: str) -> None:
        self._activity_context = context
        self._activity_phase = phase
        self._activity_elapsed.start()
        self._activity_timer.start()
        self.progress_bar.setRange(0, 0)
        self.eta_label.setText("ETA: calculating…" if context == "download" else "ETA: after download starts")
        self._refresh_activity()

    def _refresh_activity(self) -> None:
        if not self._activity_context:
            return
        elapsed = max(0, self._activity_elapsed.elapsed() // 1000)
        self.status_label.setText(f"Fetching information… {elapsed}s")
        self.details_label.setText(f"{self._activity_phase}. yt-dlp is still working; you can cancel if needed.")

    def _end_activity(self, context: str = "") -> None:
        if context and self._activity_context != context:
            return
        self._activity_context = ""
        self._activity_timer.stop()
        if self.progress_bar.maximum() == 0:
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("%p%")

    def _download_completed(self, output_path: str, _details: str) -> None:
        self._end_activity("download")
        self._set_running(False)
        self.status_label.setText("Finished")
        self.progress_bar.setValue(1000)
        self.progress_bar.setFormat("100.0%")
        self.eta_label.setText("ETA: 00:00")
        self.details_label.setText(output_path or "Download completed")
        self.statusBar().showMessage("Download finished", 8000)
        if output_path:
            self.details_label.setToolTip(output_path)

    def _download_failed(self, exit_code: int, details: str) -> None:
        self._end_activity("download")
        self._set_running(False)
        self.status_label.setText("Failed")
        self.eta_label.setText("ETA: —")
        message = friendly_error(details, exit_code)
        ErrorDialog(message, details, self).exec()

    def _download_cancelled(self) -> None:
        self._end_activity("download")
        self._set_running(False)
        self.status_label.setText("Cancelled")
        self.eta_label.setText("ETA: —")
        self.details_label.setText("The download was cancelled.")
        if self._close_after_cancel:
            self._close_after_cancel = False
            QTimer.singleShot(0, self.close)

    def _show_settings(self) -> None:
        dialog = SettingsDialog(self.settings.get("tools/ytdlp"), self.settings.get("tools/ffmpeg"), self)
        if dialog.exec():
            self.settings.set("tools/ytdlp", dialog.ytdlp_path)
            self.settings.set("tools/ffmpeg", dialog.ffmpeg_path)
            self.settings.sync()
            self._refresh_dependencies()

    def _missing_ytdlp(self, resume_action: str = "") -> None:
        answer = QMessageBox.question(
            self,
            "yt-dlp not found",
            "yt-dlp is not installed or configured. Download the latest Windows release now?\n\n"
            "It will be stored in this app's private tools folder and can be updated later.",
        )
        if answer == QMessageBox.Yes:
            self._install_ytdlp(resume_action)

    def _install_ytdlp(self, resume_action: str) -> None:
        if self.tools.busy:
            return
        self._pending_action = resume_action
        self._begin_tool_install("yt-dlp")
        self.tools.install_ytdlp()

    def _request_ffmpeg_install(self, resume_action: str) -> None:
        if self.tools.busy:
            return
        answer = QMessageBox.question(
            self,
            "Install FFmpeg",
            "This operation needs FFmpeg. Download the FFmpeg release essentials build now?\n\n"
            "Download: approximately 105 MB from gyan.dev, a Windows build provider linked by ffmpeg.org.\n"
            "The published SHA-256 checksum will be verified before ffmpeg.exe and ffprobe.exe are installed "
            "in this app's private tools folder.",
        )
        if answer != QMessageBox.Yes:
            return
        self._pending_action = resume_action
        self._begin_tool_install("FFmpeg")
        self.tools.install_ffmpeg()

    def _begin_tool_install(self, tool: str) -> None:
        self._tool_installing = tool
        self.download_button.setEnabled(False)
        self.inspect_button.setEnabled(False)
        self.options_frame.setEnabled(False)
        self.url_edit.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(f"Preparing {tool} installation…")
        self.details_label.setText("Connecting to the download provider.")
        self.eta_label.setText("ETA: calculating…")

    def _tool_message(self, message: str) -> None:
        self.statusBar().showMessage(message)
        if not self._tool_installing:
            return
        self.status_label.setText(message)
        if message.startswith("Extracting") or message.startswith("Verifying"):
            self.progress_bar.setRange(0, 0)
            self.cancel_button.setEnabled(False)
            self.eta_label.setText("ETA: finalizing…")

    def _tool_download_progress(self, tool: str, received: int, total: int) -> None:
        if not self._tool_installing:
            return
        if total > 0:
            percent = max(0.0, min(100.0, received * 100 / total))
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(round(percent * 10))
            self.progress_bar.setFormat(f"{percent:.1f}%")
            self.status_label.setText(f"Downloading {tool}… {percent:.1f}%")
            self.details_label.setText(f"{human_bytes(received)} / {human_bytes(total)}")
        else:
            self.progress_bar.setRange(0, 0)
            self.status_label.setText(f"Downloading {tool}…")

    def _finish_tool_install(self) -> str:
        pending = self._pending_action
        self._pending_action = ""
        self._tool_installing = ""
        self.download_button.setEnabled(True)
        self.inspect_button.setEnabled(True)
        self.options_frame.setEnabled(True)
        self.url_edit.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        self.eta_label.setText("ETA: —")
        return pending

    def _resume_action(self, action: str) -> None:
        if action == "download":
            QTimer.singleShot(0, self._start_download)
        elif action == "inspect":
            QTimer.singleShot(0, self._inspect_formats)

    def _install_finished(self, success: bool, message: str) -> None:
        pending = self._finish_tool_install()
        if success:
            self.settings.set("tools/ytdlp", message)
            self.settings.sync()
            self._refresh_dependencies()
            self.status_label.setText("yt-dlp installed")
            self.details_label.setText(message)
            if pending:
                self._resume_action(pending)
            else:
                information(self, "yt-dlp installed", f"yt-dlp was installed at:\n{message}")
        else:
            ErrorDialog("yt-dlp could not be installed.", message, self).exec()

    def _ffmpeg_install_finished(self, success: bool, message: str) -> None:
        pending = self._finish_tool_install()
        if success:
            self.settings.set("tools/ffmpeg", message)
            self.settings.sync()
            self._refresh_dependencies()
            self.status_label.setText("FFmpeg installed")
            self.details_label.setText(message)
            if pending:
                self._resume_action(pending)
            else:
                information(self, "FFmpeg installed", f"FFmpeg was installed at:\n{message}")
        else:
            ErrorDialog("FFmpeg could not be installed.", message, self).exec()

    def _update_ytdlp(self) -> None:
        if self.ytdlp_path:
            self.tools.update_ytdlp(self.ytdlp_path)

    def _update_finished(self, success: bool, details: str) -> None:
        if success:
            information(self, "yt-dlp update", details)
        else:
            ErrorDialog("yt-dlp could not be updated.", details, self).exec()

    def _log(self, text: str) -> None:
        self.log_dialog.append(text)

    def _warn(self, text: str) -> None:
        QMessageBox.warning(self, "Cannot continue", text)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tools.busy:
            QMessageBox.information(
                self,
                "Tool installation in progress",
                "Please wait for the tool installation to finish, or cancel the download before closing.",
            )
            event.ignore()
            return
        if self.runner.running:
            answer = QMessageBox.question(self, "Download in progress", "Cancel the active download and exit?")
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._close_after_cancel = True
            self.runner.cancel()
            event.ignore()
            return
        if self.inspector.running:
            self.inspector.cancel()
            self.inspector.process.waitForFinished(1500)
        self._save_settings()
        event.accept()
