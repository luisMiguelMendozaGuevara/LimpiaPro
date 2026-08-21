"""LimpiaPro entry point.

The code lives in the `limpiapro` package; this file remains the entry
point so LimpiaPro.bat and LimpiaPro.spec keep working unchanged.

`py -3.12 limpiador.py --qt` runs the new PySide6 interface; without the
flag the legacy customtkinter app runs (both are kept until the migration
is validated)."""

import sys

from limpiapro.app import _excepthook, main

if __name__ == "__main__":
    sys.excepthook = _excepthook
    if "--qt" in sys.argv:
        from limpiapro.app_qt import main as qt_main
        qt_main()
    else:
        main()
