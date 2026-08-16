"""Papelera de reciclaje.

Se usa la API de shell (SHQueryRecycleBinW / SHEmptyRecycleBinW) que ya
cuenta el tamano real de todas las unidades, incluyendo papeleras de otros
SIDs. Si la API falla, se recae en el recuento por carpetas $Recycle.Bin.
"""

import ctypes
import os
from ctypes import wintypes

from .utils import _folder_size


class _SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def _logical_drives():
    """Letras de unidad con raiz (p.ej. 'C:\\')."""
    drives = []
    buf = ctypes.create_unicode_buffer(261)
    n = ctypes.windll.kernel32.GetLogicalDriveStringsW(len(buf), buf)
    if n:
        drives = [d for d in buf.value.split("\x00") if d]
    return drives


def _query_recycle_bin():
    """Devuelve el tamano (en bytes) de la papelera con la API de shell,
    o None si la llamada no esta disponible / falla."""
    try:
        info = _SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(_SHQUERYRBINFO)
        total = 0
        for drive in _logical_drives():
            if not drive:
                continue
            info.i64Size = 0
            r = ctypes.windll.shell32.SHQueryRecycleBinW(drive, ctypes.byref(info))
            if r == 0:
                total += info.i64Size or 0
        return total
    except Exception:
        return None


def recycle_bin_size():
    size = _query_recycle_bin()
    if size is not None:
        return size
    # fallback: recorrer las carpetas $Recycle.Bin de cada unidad
    total = 0
    for drive in _logical_drives():
        root = os.path.join(drive, "$Recycle.Bin")
        if os.path.isdir(root):
            total += _folder_size(root)
    return total


def empty_recycle_bin():
    try:
        # SHERB_NOCONFIRMATION | SHERB_NOSOUND: la app ya pide confirmacion
        # y no debe reproducir el sonido de vaciado.
        flags = 0x00000001 | 0x00000004
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        if result in (0, 5):
            return True, "Papelera vaciada."
        return False, f"Error al vaciar papelera (codigo {result})."
    except Exception as e:
        return False, str(e)