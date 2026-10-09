"""Require the frozen application to display its window and report readiness.

A running process alone is insufficient: PyInstaller's error dialog keeps a
failed application alive indefinitely. Run with only Windows DLLs on PATH so
development tools cannot supply missing dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def verify(executable: Path, timeout: int = 45) -> dict:
    executable = executable.resolve(strict=True)
    environment = os.environ.copy()
    windows = Path(environment.get("SystemRoot", "C:/Windows"))
    environment["PATH"] = os.pathsep.join((str(windows / "System32"), str(windows)))
    for key in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM", "PYTHONPATH", "PYTHONHOME"):
        environment.pop(key, None)
    # A fresh working directory also checks that no neighboring DLL is needed.
    with tempfile.TemporaryDirectory(prefix="ytdlp-gui-smoke-") as directory:
        report_path = Path(directory) / "ready.json"
        process = subprocess.Popen([str(executable), "--smoke-test", str(report_path)],
            cwd=directory, env=environment)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            subprocess.run([str(windows / "System32/taskkill.exe"), "/PID", str(process.pid), "/T", "/F"],
                capture_output=True, check=False)
            process.wait(timeout=10)
            raise RuntimeError("Packaged app did not report readiness; it may be showing a startup error dialog") from exc
        if code != 0 or not report_path.is_file():
            raise RuntimeError(f"Packaged app failed startup (exit {code}); no successful readiness report")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") != "ok" or report.get("platform") != "windows" or report.get("section") != [90, 120]:
            raise RuntimeError(f"Packaged app did not pass the Windows UI check: {report}")
    report["sha256"] = hashlib.sha256(executable.read_bytes()).hexdigest()
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--timeout", type=int, default=45)
    arguments = parser.parse_args()
    try:
        print(json.dumps(verify(arguments.executable, arguments.timeout), indent=2))
    except (RuntimeError, OSError) as exc:
        parser.exit(1, f"Startup verification FAILED: {exc}\n")
