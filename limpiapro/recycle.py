"""Papelera de reciclaje."""

import ctypes
import os

from .utils import _folder_size


def recycle_bin_size():
    total = 0
    for root in ("C:\\$Recycle.Bin", "D:\\$Recycle.Bin",
                 "E:\\$Recycle.Bin", "F:\\$Recycle.Bin"):
        if os.path.isdir(root):
            total += _folder_size(root)
    return total


def empty_recycle_bin():
    try:
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0)
        if result in (0, 5):
            return True, "Papelera vaciada."
        return False, f"Error al vaciar papelera (codigo {result})."
    except Exception as e:
        return False, str(e)
