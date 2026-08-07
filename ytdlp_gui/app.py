from __future__ import annotations

import sys

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> int:
    QCoreApplication.setOrganizationName("OpenUtility")
    QCoreApplication.setApplicationName("yt-dlp GUI")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()
