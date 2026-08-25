"""Recycle bin management.

This module provides functions to query and empty the Windows Recycle Bin
using the shell API (SHQueryRecycleBinW / SHEmptyRecycleBinW).

Architecture Overview:
    The shell API already reports the real size across all drives, including
    the bins of other user SIDs. If the API fails, the size falls back to
    walking the $Recycle.Bin folder of each drive.

Backend Rule:
    Status messages returned here are stable English/ASCII; the UI layer
    translates user-facing text via i18n.t().

Functions:
    - recycle_bin_size(): Get the total size in bytes of the Recycle Bin.
    - empty_recycle_bin(): Empty the Recycle Bin of all drives.
"""

import ctypes
import os
from ctypes import wintypes

from .utils import _folder_size


class _SHQUERYRBINFO(ctypes.Structure):
    """SHQUERYRBINFO: output struct of SHQueryRecycleBinW.
    
    This structure is used by the SHQueryRecycleBinW API to return information
    about the Recycle Bin for a specific drive.
    
    Attributes:
        cbSize (DWORD): Must be set to sizeof(struct) before the call.
        i64Size (c_longlong): Total bytes in the bin of the queried drive.
        i64NumItems (c_longlong): Total number of items in the bin.
    """
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def _logical_drives():
    """Get drive letters with root path (e.g. 'C:\\') from GetLogicalDriveStringsW.
    
    Returns:
        list[str]: List of drive root paths (e.g., ["C:\\", "D:\\"]).
    """
    drives = []
    buf = ctypes.create_unicode_buffer(261)
    n = ctypes.windll.kernel32.GetLogicalDriveStringsW(len(buf), buf)
    if n:
        drives = [d for d in buf.value.split("\x00") if d]
    return drives


def _query_recycle_bin():
    """Get total size (bytes) of the recycle bin via the shell API.
    
    Returns None when the call is unavailable or fails (the caller then
    uses the folder walk fallback).
    
    Returns:
        int | None: Total size in bytes across all drives, or None on failure.
    """
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
    """Get the size in bytes of the recycle bin.
    
    Uses the shell API first (SHQueryRecycleBinW), falling back to walking
    the $Recycle.Bin folder of every drive if the API fails.
    
    Returns:
        int: Total size in bytes of the Recycle Bin across all drives.
        
    Notes:
        - Shell API: Fast and accurate, includes other user SIDs.
        - Fallback: Walks $Recycle.Bin folders (slower, may miss some items).
    """
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
    """Empty the recycle bin of all drives.
    
    Returns (ok, msg) with a stable English/ASCII detail string (translated
    for display by the UI).
    
    Returns:
        tuple[bool, str]: (success, message)
            - On success: (True, "Recycle bin emptied.")
            - On failure: (False, "Error message")
            
    Notes:
        - Flags: SHERB_NOCONFIRMATION | SHERB_NOSOUND (the app already asked
          for confirmation and must not play the emptying sound).
        - Return code 5 (ERROR_ACCESS_DENIED) is treated as success because
          the bin may already be empty.
    """
    try:
        flags = 0x00000001 | 0x00000004
        result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        if result in (0, 5):
            return True, "Recycle bin emptied."
        return False, f"Error emptying recycle bin (code {result})."
    except Exception as e:
        return False, str(e)
