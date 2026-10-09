import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QProcess, QTimer
from PySide6.QtWidgets import QApplication

from ytdlp_gui.external_process import prepare_external_process
from ytdlp_gui.tool_manager import ToolManager


class FakeUpdater:
    def __init__(self):
        self.launches = []
        self.killed = False

    def setProcessEnvironment(self, environment):
        self.environment = environment

    def start(self, executable, args):
        self.launches.append((executable, args))

    def readAllStandardOutput(self):
        return b"yt-dlp is up to date"

    def errorString(self):
        return "could not launch"

    def kill(self):
        self.killed = True


@pytest.fixture
def updater(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    from ytdlp_gui import tool_manager
    target = tmp_path / "app-tools" / "yt-dlp.exe"
    target.parent.mkdir()
    source = tmp_path / "system-yt-dlp.exe"
    source.write_bytes(b"original tool")
    monkeypatch.setattr(tool_manager, "ytdlp_download_target", lambda: target)
    manager = ToolManager()
    manager._update_process = FakeUpdater()
    results = []
    manager.update_finished.connect(lambda ok, details: results.append((ok, details)))
    yield manager, source, target, results
    manager._update_timer.stop()
    app.processEvents()


def test_updates_private_copy_and_blocks_concurrent_tool_work(updater):
    manager, source, target, results = updater
    manager.update_ytdlp(str(source))
    assert target.read_bytes() == source.read_bytes()
    assert manager._update_process.launches == [(str(target), ["--ignore-config", "--socket-timeout", "15", "-U"])]
    assert manager.busy and manager.can_cancel
    manager.update_ytdlp(str(source))
    manager.install_ytdlp()
    assert len(manager._update_process.launches) == 1
    assert manager._reply is None
    manager._update_done(0, QProcess.NormalExit)
    assert results == [(True, "yt-dlp is up to date")]
    assert not manager.busy and not manager._update_timer.isActive()
    assert source.read_bytes() == b"original tool"
    assert manager.updated_ytdlp_path == str(target)


def test_failed_updater_start_completes_once_and_releases_controls(updater):
    manager, source, _, results = updater
    manager.update_ytdlp(str(source))
    manager._update_error(QProcess.FailedToStart)
    manager._update_done(1, QProcess.NormalExit)
    assert len(results) == 1 and not results[0][0]
    assert not manager.busy


@pytest.mark.parametrize("action, message", [("cancel_install", "cancelled"), ("_update_timeout", "timed out")])
def test_update_cancellation_and_timeout_preserve_existing_tool(updater, action, message):
    manager, source, target, results = updater
    manager.update_ytdlp(str(source))
    getattr(manager, action)()
    assert manager._update_process.killed
    manager._update_done(1, QProcess.CrashExit)
    assert not results[0][0] and message in results[0][1]
    assert source.read_bytes() == target.read_bytes() == b"original tool"
    assert not manager.busy


def test_ssl_context_works_despite_unwritable_inherited_keylog_path(monkeypatch):
    app = QApplication.instance() or QApplication([])
    # A directory cannot be used as a key-log file and reproduces HTTPS failure.
    monkeypatch.setenv("SSLKEYLOGFILE", str(Path(__file__).parent))
    monkeypatch.setenv("HTTPS_PROXY", "http://example.com:3128")
    process = QProcess()
    prepare_external_process(process)
    assert not process.processEnvironment().contains("SSLKEYLOGFILE")
    assert process.processEnvironment().value("HTTPS_PROXY") == "http://example.com:3128"
    loop = QEventLoop()
    process.finished.connect(loop.quit)
    process.start(sys.executable, ["-c", "import ssl; ssl.create_default_context(); print('SSL ready')"])
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(5000)
    loop.exec()
    assert process.state() == QProcess.NotRunning
    assert process.exitCode() == 0, bytes(process.readAllStandardError()).decode()
    assert b"SSL ready" in bytes(process.readAllStandardOutput())
    assert app is not None


@pytest.mark.parametrize("success", [True, False])
def test_automatic_update_is_quiet_and_restores_download_controls(monkeypatch, updater, success):
    from ytdlp_gui import main_window
    manager, source, target, _ = updater

    class MemorySettings:
        output_folder = str(source.parent)

        def __init__(self):
            self.values = {}

        def get(self, key, default=""):
            return self.values.get(key, default)

        def get_bool(self, key, default=False):
            return self.values.get(key, default)

        def set(self, key, value):
            self.values[key] = value

        def sync(self):
            pass

    monkeypatch.setattr(main_window, "AppSettings", MemorySettings)
    monkeypatch.setattr(main_window, "ToolManager", lambda _: manager)
    monkeypatch.setattr(main_window, "find_ytdlp", lambda configured: configured or str(source))
    monkeypatch.setattr(main_window, "find_ffmpeg", lambda _: "")
    def unexpected_dialog(*args):
        pytest.fail("Automatic startup updates should not show a modal dialog")
    monkeypatch.setattr(main_window, "information", unexpected_dialog)
    monkeypatch.setattr(main_window, "ErrorDialog", unexpected_dialog)
    window = main_window.MainWindow()
    try:
        window._update_ytdlp(automatic=True)
        assert manager.busy
        assert not window.download_button.isEnabled()
        assert not window.inspect_button.isEnabled()
        assert not window.update_action.isEnabled()
        assert window.cancel_button.isEnabled()
        window._start_download()
        window._inspect_formats()
        assert not window.runner.running and not window.inspector.running
        manager._update_done(0 if success else 1, QProcess.NormalExit)
        assert window.download_button.isEnabled() and window.inspect_button.isEnabled()
        assert not window.cancel_button.isEnabled()
        assert window.ytdlp_path == str(target if success else source)
    finally:
        window.close()
