from PySide6.QtCore import QCoreApplication, QProcess

from ytdlp_gui.process_runner import ProcessRunner


def test_http_403_is_retried_once_over_ipv4() -> None:
    app = QCoreApplication.instance() or QCoreApplication([])
    runner = ProcessRunner()
    launches: list[tuple[str, list[str]]] = []
    runner._launch = lambda program, args: launches.append((program, args))  # type: ignore[method-assign]
    runner._program = "yt-dlp"
    runner._args = ["--no-playlist", "https://example.com/video"]
    runner._log = ["ERROR: unable to download video data: HTTP Error 403: Forbidden"]

    runner._finished(1, QProcess.NormalExit)
    app.processEvents()

    assert launches == [
        (
            "yt-dlp",
            ["--force-ipv4", "--no-playlist", "https://example.com/video"],
        )
    ]
    assert runner._retried_with_ipv4


def test_http_403_is_not_retried_when_ipv4_was_already_forced() -> None:
    QCoreApplication.instance() or QCoreApplication([])
    runner = ProcessRunner()
    failures: list[tuple[int, str]] = []
    runner.failed.connect(lambda code, details: failures.append((code, details)))
    runner._program = "yt-dlp"
    runner._args = ["--force-ipv4", "https://example.com/video"]
    runner._log = ["ERROR: HTTP Error 403: Forbidden"]

    runner._finished(1, QProcess.NormalExit)

    assert failures and failures[0][0] == 1
