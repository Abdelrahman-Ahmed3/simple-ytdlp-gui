from __future__ import annotations

import sys
import json
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer, qVersion
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from . import __version__


def main() -> int:
    QCoreApplication.setOrganizationName("OpenUtility")
    QCoreApplication.setApplicationName("yt-dlp GUI")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        report_path = Path(sys.argv[2])

        def report_startup() -> None:
            try:
                if not window.isVisible() or not window.windowHandle().isExposed():
                    raise RuntimeError("Main window was not displayed")
                # Exercise the actual section controls without saving changes.
                window.section_check.setChecked(True)
                window.start_edit.setText("1:30")
                window.end_edit.setText("2:00")
                options = window._options()
                if (options.section_start, options.section_end) != (90, 120):
                    raise RuntimeError("Section controls did not produce the requested range")
                report_path.write_text(json.dumps({"status": "ok", "version": __version__,
                    "qt_version": qVersion(), "window_title": window.windowTitle(),
                    "platform": app.platformName(), "section": [90, 120]}), encoding="utf-8")
            except Exception as exc:
                report_path.write_text(json.dumps({"status": "failed", "error": str(exc)}), encoding="utf-8")
                app.exit(1)
                return
            app.exit(0)

        QTimer.singleShot(1000, report_startup)
    return app.exec()
