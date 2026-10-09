"""Keep external download tools independent of the frozen GUI runtime."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment


def prepare_external_process(process: QProcess) -> None:
    environment = QProcessEnvironment.systemEnvironment()
    # SSLKEYLOGFILE can refer to a launcher/sandbox-only file. Python's HTTPS
    # clients open it during SSL setup, failing before any network request.
    for name in ("SSLKEYLOGFILE", "PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QML2_IMPORT_PATH"):
        environment.remove(name)
    environment.insert("PYINSTALLER_RESET_ENVIRONMENT", "1")
    if getattr(sys, "frozen", False):
        bundle = os.path.normcase(os.path.abspath(sys._MEIPASS))
        paths = environment.value("PATH").split(os.pathsep)
        environment.insert("PATH", os.pathsep.join(path for path in paths
            if path and not os.path.normcase(os.path.abspath(path)).startswith(bundle + os.sep)
            and os.path.normcase(os.path.abspath(path)) != bundle))
        if os.name == "nt":
            # PyInstaller's DLL directory is inherited by child processes.
            # Qt is already loaded; external tools must resolve their own DLLs.
            import ctypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
            kernel32.SetDllDirectoryW.restype = ctypes.c_int
            if not kernel32.SetDllDirectoryW(None):
                raise ctypes.WinError(ctypes.get_last_error())
    process.setProcessEnvironment(environment)
