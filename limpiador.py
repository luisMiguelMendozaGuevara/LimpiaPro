"""Punto de entrada de LimpiaPro.

El codigo vive en el paquete `limpiapro`; este archivo se mantiene como
entrada para que LimpiaPro.bat y LimpiaPro.spec sigan funcionando igual."""

import sys

from limpiapro.app import _excepthook, main

if __name__ == "__main__":
    sys.excepthook = _excepthook
    main()
