import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from ytdlp_gui.format_inspector import FormatInspector
from ytdlp_gui.models import ProgressUpdate


def test_failed_process_start_is_reported_once() -> None:
    app = QApplication.instance() or QApplication([])
    loop = QEventLoop()
    inspector = FormatInspector()
    failures: list[str] = []

    def failed(message: str) -> None:
        failures.append(message)
        loop.quit()

    inspector.failed.connect(failed)
    inspector.inspect("definitely-not-a-real-ytdlp-executable", "https://example.com/video")
    QTimer.singleShot(3000, loop.quit)
    loop.exec()

    assert len(failures) == 1
    assert failures[0].startswith("Could not start yt-dlp:")
    assert app is not None


def test_activity_lines_are_translated_for_the_main_ui() -> None:
    from ytdlp_gui.main_window import MainWindow

    assert MainWindow._activity_phase_from_log("[youtube] Downloading webpage") == "Loading the webpage"
    assert "player API" in MainWindow._activity_phase_from_log("Downloading android player API JSON")
    assert MainWindow._activity_phase_from_log("unrelated debug line") == ""


def test_progress_bar_and_explicit_eta_are_updated() -> None:
    from ytdlp_gui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._begin_activity("download", "Starting yt-dlp")
    window._show_progress(
        ProgressUpdate(
            percent=42.5,
            speed="12.4 MiB/s",
            downloaded=54_525_952,
            total=134_217_728,
            eta="00:06",
            operation="Downloading video",
        )
    )

    assert window.progress_bar.minimum() == 0
    assert window.progress_bar.maximum() == 1000
    assert window.progress_bar.value() == 425
    assert window.progress_bar.format() == "42.5%"
    assert window.eta_label.text() == "ETA: 00:06"
    window.close()
    assert app is not None
