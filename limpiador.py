"""LimpiaPro entry point.

The code lives in the `limpiapro` package; this file remains the entry
point so LimpiaPro.bat and LimpiaPro.spec keep working unchanged."""

import sys

from limpiapro.app import _excepthook, main

if __name__ == "__main__":
    sys.excepthook = _excepthook
    main()
