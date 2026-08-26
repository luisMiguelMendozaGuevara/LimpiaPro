"""LimpiaPro entry point.

The code lives in the `limpiapro` package; this file remains the entry
point so LimpiaPro.bat and LimpiaPro.spec keep working unchanged.

The PySide6 interface is the only interface (the CustomTkinter app and
its `--legacy` flag were removed; the legacy code lives on the
`legacy-tk-2.4` tag).
"""

import sys
import traceback

from limpiapro.utils import _errlog


def _excepthook(exc_type, exc, tb):
    """sys.excepthook: log uncaught exceptions (packaged app has no console)."""
    _errlog("uncaught exception: "
            + "".join(traceback.format_exception(exc_type, exc, tb)))


if __name__ == "__main__":
    sys.excepthook = _excepthook
    from limpiapro.app_qt import main as qt_main
    qt_main()
