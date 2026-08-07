from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Debug log")
        self.resize(760, 480)
        layout = QVBoxLayout(self)
        self.editor = QTextEdit(readOnly=True)
        self.editor.setLineWrapMode(QTextEdit.NoWrap)
        self.editor.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        layout.addWidget(self.editor)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy_button = buttons.addButton("Copy all", QDialogButtonBox.ActionRole)
        clear_button = buttons.addButton("Clear", QDialogButtonBox.ResetRole)
        copy_button.clicked.connect(lambda: self.editor.selectAll() or self.editor.copy())
        clear_button.clicked.connect(self.editor.clear)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def append(self, text: str) -> None:
        self.editor.moveCursor(QTextCursor.End)
        self.editor.insertPlainText(text + "\n")
        self.editor.ensureCursorVisible()


class ErrorDialog(QDialog):
    def __init__(self, message: str, details: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Download failed")
        self.resize(620, 240)
        layout = QVBoxLayout(self)
        title = QLabel(message)
        title.setWordWrap(True)
        title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(title)
        self.details = QTextEdit(details, readOnly=True)
        self.details.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self.details.setLineWrapMode(QTextEdit.NoWrap)
        self.details.setVisible(False)
        layout.addWidget(self.details, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        details_button = buttons.addButton("Show technical details", QDialogButtonBox.ActionRole)
        copy_button = buttons.addButton("Copy details", QDialogButtonBox.ActionRole)

        def toggle() -> None:
            visible = not self.details.isVisible()
            self.details.setVisible(visible)
            details_button.setText("Hide technical details" if visible else "Show technical details")
            self.resize(760, 520 if visible else 240)

        details_button.clicked.connect(toggle)
        copy_button.clicked.connect(lambda: self.details.selectAll() or self.details.copy())
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class PathRow(QWidget):
    def __init__(self, value: str, file_filter: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.edit = QLineEdit(value)
        button = QPushButton("Browse…")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)
        button.clicked.connect(lambda: self._browse(file_filter))

    def _browse(self, file_filter: str) -> None:
        current = self.edit.text()
        selected, _ = QFileDialog.getOpenFileName(self, "Select executable", current, file_filter)
        if selected:
            self.edit.setText(str(Path(selected)))


class SettingsDialog(QDialog):
    def __init__(self, ytdlp_path: str, ffmpeg_path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(650, 170)
        layout = QVBoxLayout(self)
        note = QLabel("Leave a path empty to search the app tools folder and system PATH automatically.")
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.ytdlp = PathRow(ytdlp_path, "Executables (yt-dlp.exe yt-dlp);;All files (*)")
        self.ffmpeg = PathRow(ffmpeg_path, "Executables (ffmpeg.exe ffmpeg);;All files (*)")
        form.addRow("yt-dlp:", self.ytdlp)
        form.addRow("FFmpeg:", self.ffmpeg)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def ytdlp_path(self) -> str:
        return self.ytdlp.edit.text().strip()

    @property
    def ffmpeg_path(self) -> str:
        return self.ffmpeg.edit.text().strip()


def information(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)
