from __future__ import annotations

import sys
import json
import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QProcess, QTimer, qVersion
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from . import __version__
from .external_process import prepare_external_process


def main() -> int:
    QCoreApplication.setOrganizationName("OpenUtility")
    QCoreApplication.setApplicationName("yt-dlp GUI")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    if len(sys.argv) == 3 and sys.argv[1] in {"--smoke-test", "--smoke-test-update"}:
        report_path = Path(sys.argv[2])
        update_check = sys.argv[1] == "--smoke-test-update"
        update_result = None

        def report_startup() -> None:
            try:
                if update_check and update_result is not True:
                    raise RuntimeError("Packaged startup update did not succeed")
                if not window.isVisible() or not window.windowHandle().isExposed():
                    raise RuntimeError("Main window was not displayed")
                # Exercise the actual section controls without saving changes.
                window.section_check.setChecked(True)
                window.start_edit.setText("1:30")
                window.end_edit.setText("2:00")
                options = window._options()
                if (options.section_start, options.section_end) != (90, 120):
                    raise RuntimeError("Section controls did not produce the requested range")
                external_tools = {}
                for name, executable, arguments in (
                    ("yt-dlp", window.ytdlp_path, ["--version"]),
                    ("ffmpeg", window.ffmpeg_path, ["-version"]),
                ):
                    if not executable:
                        continue
                    process = QProcess()
                    prepare_external_process(process)
                    process.start(executable, arguments)
                    if not process.waitForFinished(15000) or process.exitCode() != 0:
                        process.kill()
                        process.waitForFinished(3000)
                        raise RuntimeError(f"Packaged app could not launch {name}")
                    external_tools[name] = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").splitlines()[0]
                report_path.write_text(json.dumps({"status": "ok", "version": __version__,
                    "qt_version": qVersion(), "window_title": window.windowTitle(),
                    "platform": app.platformName(), "section": [90, 120], "external_tools": external_tools,
                    "startup_update": update_result}), encoding="utf-8")
            except Exception as exc:
                report_path.write_text(json.dumps({"status": "failed", "error": str(exc)}), encoding="utf-8")
                app.exit(1)
                return
            app.exit(0)

        if update_check:
            # Explicit diagnostic override permits verification with Windows-only
            # PATH while still testing the real startup updater and saved path.
            window.ytdlp_path = os.environ.get("YTDLP_GUI_VERIFY_YTDLP", window.ytdlp_path)

            def updated(success: bool, _details: str) -> None:
                nonlocal update_result
                update_result = success
                QTimer.singleShot(1000, report_startup)

            window.tools.update_finished.connect(updated)
            if window.ytdlp_path:
                QTimer.singleShot(0, lambda: window._update_ytdlp(automatic=True))
            else:
                QTimer.singleShot(1000, report_startup)
        else:
            QTimer.singleShot(1000, report_startup)
    else:
        QTimer.singleShot(0, lambda: window._update_ytdlp(automatic=True))
    return app.exec()
