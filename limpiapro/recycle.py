"""Recycle bin management.

The shell API (SHQueryRecycleBinW / SHEmptyRecycleBinW) already reports
the real size across all drives, including the bins of other user SIDs.
If the API fails, the size falls back to walking the $Recycle.Bin folder
of each drive.

Backend rule: status messages returned here are stable English/ASCII; the
UI layer translates user-facing text via i18n.t()."""

import ctypes
import os
from ctypes import wintypes

from .utils import _folder_size


class _SHQUERYRBINFO(ctypes.Structure):
    """SHQUERYRBINFO: output struct of SHQueryRecycleBinW.

    cbSize must be set to sizeof(struct) before the call; i64Size holds the
    total bytes in the bin of the queried drive."""
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def _logical_drives():
    """Drive letters with root path (e.g. 'C:\\') from GetLogicalDriveStringsW."""
    drives = []
    buf = ctypes.create_unicode_buffer(261)
    n = ctypes.windll.kernel32.GetLogicalDriveStringsW(len(buf), buf)
    if n:
        drives = [d for d in buf.value.split("\x00") if d]
    return drives


def _query_recycle_bin():
    """Total size (bytes) of the recycle bin via the shell API, or None when
    the call is unavailable / fails (the caller then uses the folder walk)."""
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
    """Size in bytes of the recycle bin (shell API first, folder walk as
    fallback)."""
    size = _query_recycle_bin()
    if size is not None:
        return size
    # fallback: walk the $Recycle.Bin folder of every drive
    total = 0
    for drive in _logical_drives():
        root = os.path.join(drive, "$Recycle.Bin")
        if os.path.isdir(root):
            total += _folder_size(root)
    return total


def empty_recycle_bin():
    """Empty the recycle bin of all drives. Returns (ok, msg) with a stable
    English/ASCII detail string (translated for display by the UI).

    SHERB_NOCONFIRMATION | SHERB_NOSOUND: the app already asked for
    confirmation and must not play the emptying sound."""
    try:
        flags = 0x00000001 | 0x00000004
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        if result in (0, 5):
            return True, "Recycle bin emptied."
        return False, f"Error emptying recycle bin (code {result})."
    except Exception as e:
        return False, str(e)
