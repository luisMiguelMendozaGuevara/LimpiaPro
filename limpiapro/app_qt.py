"""PySide6 entry point (limpiador.py --qt).

This module is the bootstrap for the modern PySide6-based user interface.
It mirrors the legacy bootstrap in app.py with the following responsibilities:

1. **UAC Elevation**: Re-launches the application with administrator privileges
   if not already elevated. If the user declines UAC, the app continues without
   admin (some features will be limited).

2. **Application Initialization**: Creates the QApplication, sets metadata
   (name, version, icon), applies the theme, and shows the main window.

3. **Smoke Testing**: Supports --smoke-test flag for CI/CD to verify the
   application graph can be built without a window.

Architecture Notes:
    - Worker threads come from the controller, so the UI thread only renders.
    - The main window is created synchronously on the UI thread.
    - All heavy operations (scanning, deletion) are delegated to QThread workers
      in the controller to keep the UI responsive.

Entry Points:
    - `main()`: Primary entry point called from limpiador.py when --qt is specified.
    - `_maybe_elevate()`: Internal helper for UAC elevation.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys

from . import APP_NAME, APP_VERSION
from .utils import _errlog, is_admin


def _maybe_elevate() -> bool:
    """Re-launch elevated when not admin; True when a new instance was launched.
    
    Uses ShellExecuteW with the "runas" verb to trigger UAC elevation. If the
    user accepts, a new elevated instance is launched and this instance should
    exit. If the user declines, the function returns False and the current
    instance continues without admin privileges.
    
    Returns:
        bool: True if a new elevated instance was launched (caller should exit),
              False if elevation was declined or failed (caller should continue).
              
    Notes:
        - Frozen detection: Handles both packaged (PyInstaller) and development modes.
        - Argument passing: Uses subprocess.list2cmdline to properly escape arguments.
        - Error logging: All elevation attempts are logged to limpiapro_error.log.
        - ShellExecuteW return value: > 32 indicates success, <= 32 indicates failure.
    """
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
    """PySide6 application entry point.
    
    This is the main function called when the application is launched with
    the --qt flag. It handles:
    - Command-line flags (--version, --smoke-test)
    - UAC elevation (if not admin)
    - QApplication initialization
    - Theme application
    - Main window creation and display
    
    Notes:
        - --version: Prints version and exits.
        - --smoke-test: Builds the application graph without a window (for CI/CD).
        - Error logging: All startup steps are logged to limpiapro_error.log.
        - sys.exit(): Uses app.exec() return code for proper exit status.
    """
    if "--version" in sys.argv:
        print(f"{APP_NAME} {APP_VERSION}")
        return
    if "--smoke-test" in sys.argv:
        # Build the application graph without a window (packaged CI).
        from .controller import LimpiaProController
        LimpiaProController()
        print(f"{APP_NAME} qt smoke test passed")
        return
    screenshot = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--screenshot" and i + 1 < len(sys.argv):
            screenshot = sys.argv[i + 1]
    if screenshot:
        # Debug/CI: render the real window offscreen (no UAC, no console)
        # and save a PNG, so the frozen build's actual look is verifiable.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _errlog("--- qt startup ---")
    if (not screenshot and not is_admin()
            and os.environ.get("QT_QPA_PLATFORM") != "offscreen"
            and _maybe_elevate()):
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
    if screenshot:
        from PySide6.QtCore import QTimer

        def _grab() -> None:
            window.grab().save(screenshot)
            _errlog(f"qt: screenshot saved to {screenshot}")
            app.quit()

        QTimer.singleShot(2500, _grab)
        app.exec()
        return
    sys.exit(app.exec())
