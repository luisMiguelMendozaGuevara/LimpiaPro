"""LimpiaPro entry point.

The code lives in the `limpiapro` package; this file remains the entry
point so LimpiaPro.bat and LimpiaPro.spec keep working unchanged.

The PySide6 interface is the default (the migration is complete); the
legacy customtkinter app stays available with `--legacy` (it is kept
until the PySide6 UI is validated in real use). `--qt` is accepted as an
explicit alias of the default."""

import sys

from limpiapro.app import _excepthook, main

if __name__ == "__main__":
    sys.excepthook = _excepthook
    if "--legacy" in sys.argv:
        main()
    else:
        from limpiapro.app_qt import main as qt_main
        qt_main()
