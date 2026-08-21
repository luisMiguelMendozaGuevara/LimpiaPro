"""PySide6 entry point (limpiador.py --qt).

Mirrors the legacy bootstrap in app.py: re-elevate to administrator when
possible (continuing without admin if UAC is declined), then run the Qt
interface. Worker threads come from the controller, so the UI thread
only renders."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys

from . import APP_NAME, APP_VERSION
from .utils import _errlog, is_admin


def _maybe_elevate() -> bool:
    """Re-launch elevated when not admin; True when a new instance was
    launched (the caller should return)."""
    if is_admin():
        return False
    try:
        if getattr(sys, "frozen", False):
            exe, args = sys.executable, subprocess.list2cmdline(sys.argv[1:])
        else:
            exe = sys.executable
            args = subprocess.list2cmdline([os.path.abspath(sys.argv[0])]
                                           + sys.argv[1:])
        _errlog(f"qt: no admin; elevating: {exe} {args}")
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", exe, args, None, 1)
        _errlog(f"qt: runas returned {result}")
        return result > 32
    except Exception as e:
        _errlog(f"qt: elevation error: {e}")
        return False


def main() -> None:
    """PySide6 application entry point."""
    if "--version" in sys.argv:
        print(f"{APP_NAME} {APP_VERSION}")
        return
    if "--smoke-test" in sys.argv:
        # Build the application graph without a window (packaged CI).
        from .controller import LimpiaProController
        LimpiaProController()
        print(f"{APP_NAME} qt smoke test passed")
        return
    _errlog("--- qt startup ---")
    if not is_admin() and _maybe_elevate():
        return
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from .ui.main_window import MainWindow
    from .ui.theme import apply_theme
    from .utils import app_dir

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    icon_path = os.path.join(app_dir(), "assets", "limpiadora.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    apply_theme(app)
    window = MainWindow()
    window.show()
    _errlog("qt: main window shown")
    sys.exit(app.exec())
