"""Startup applications (Run/RunOnce registry keys + startup folders).

This module provides functionality to list, enable, and disable startup
entries in Windows. It handles both registry-based entries and files in
the startup folders.

Design Principles:
1. Non-Destructive Disabling:
   - Registry entries are MOVED to a parallel *Disabled key, not deleted.
   - Startup folder files are RENAMED with a .disabled extension.
   This allows the user to re-enable them later without data loss.

2. Atomic Registry Transfers:
   The _reg_transfer function ensures that a move operation never leaves
   an entry duplicated in both the active and disabled keys. If the
   deletion from the source fails, the destination is rolled back.

3. Safety:
   - RunOnce entries are flagged with a special message so the UI can
     warn the user that disabling them may prevent one-time tasks
     (like installer finalization) from ever running.
"""

import contextlib
import os
import winreg

# Single source list: (hive, active key, disabled key, display label).
# This tuple is the single source of truth for all startup registry paths.
_RUN_PAIRS = [
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Run",
     r"Software\Microsoft\Windows\CurrentVersion\RunDisabled",
     "Usuario (HKCU Run)"),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
     r"Software\Microsoft\Windows\CurrentVersion\RunOnceDisabled",
     "Usuario (HKCU RunOnce)"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Run",
     r"Software\Microsoft\Windows\CurrentVersion\RunDisabled",
     "Sistema (HKLM Run)"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\RunOnce",
     r"Software\Microsoft\Windows\CurrentVersion\RunOnceDisabled",
     "Sistema (HKLM RunOnce)"),
]

# Active keys (for listing startup apps).
RUN_KEYS = [(h, a, src) for h, a, _d, src in _RUN_PAIRS]

# Disabled keys (for the "re-enable" list).
RUN_KEYS_DISABLED = [(h, d, "Usuario (desactivadas)") for h, _a, d, _s in _RUN_PAIRS]

# Map: (hive, active key) -> (hive, disabled key).
# This lookup table allows quick resolution of the disabled counterpart
# for any given active key.
RUN_KEY_TO_DISABLED = {(h, a): (h, d) for h, a, d, _s in _RUN_PAIRS}

STARTUP_FOLDERS = [
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
    os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\StartUp"),
]


def _read_reg_entries(hive, subkey):
    """All values of a registry key as {name: value} ({} on any error).

    Args:
        hive: The registry hive (e.g., HKEY_CURRENT_USER).
        subkey: The subkey path string.

    Returns:
        dict: A dictionary of {value_name: value_data}. Empty dict on failure.
    """
    out = {}
    try:
        with winreg.OpenKey(hive, subkey) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    out[name] = value
                    i += 1
                except OSError:  # noqa: PERF203 - end of enumeration must break here
                    # End of enumeration or error.
                    break
    except OSError:
        # Key does not exist or access denied.
        pass
    return out


def _read_reg_value(hive, subkey, name):
    """Read a single value without enumerating the whole key.

    Args:
        hive: The registry hive.
        subkey: The subkey path string.
        name: The name of the value to read.

    Returns:
        The value data, or None if the value does not exist or an error occurs.
    """
    try:
        with winreg.OpenKey(hive, subkey) as key:
            try:
                val, _ = winreg.QueryValueEx(key, name)
                return val
            except OSError:
                return None
    except OSError:
        return None


def get_startup_apps():
    """List active startup applications (registry entries + startup
    folder files). Each entry dict carries its origin so set_startup can
    move it back and forth.

    Returns:
        list[dict]: A list of dictionaries, each representing a startup entry.
                    Keys include: type ("reg"|"file"), name, command, source,
                    hive/subkey (for reg), folder (for file), enabled (bool).
    """
    entries = []
    
    # 1. Enumerate active registry entries from all configured keys.
    for hive, subkey, src in RUN_KEYS:
        for name, value in _read_reg_entries(hive, subkey).items():
            entries.append({"type": "reg", "name": name, "command": str(value),
                            "source": src, "hive": hive, "subkey": subkey, "enabled": True})
                            
    # 2. Enumerate files in the startup folders.
    for folder in STARTUP_FOLDERS:
        if os.path.isdir(folder):
            for fname in os.listdir(folder):
                # Only consider common executable/script extensions.
                if fname.lower().endswith((".lnk", ".exe", ".cmd", ".bat", ".vbs")):
                    path = os.path.join(folder, fname)
                    entries.append({"type": "file", "name": fname, "command": path,
                                    "source": "Carpeta de inicio", "folder": folder,
                                    "enabled": True})
    return entries


def get_disabled_startup():
    """Applications the user has disabled (for re-enabling).

    Registry: values present in a *Disabled key and no longer in the
    active one (entries duplicated in both are ignored: an earlier
    disable that failed to delete from the active key). Files: those
    renamed with a '.disabled' extension.

    Returns:
        list[dict]: A list of disabled startup entries. Same structure
                    as get_startup_apps(), but with enabled=False.
    """
    entries = []
    
    # 1. Registry disabled entries.
    for (hive, subkey), (dhive, dsubkey) in RUN_KEY_TO_DISABLED.items():
        active_names = set(_read_reg_entries(hive, subkey).keys())
        for name, value in _read_reg_entries(dhive, dsubkey).items():
            # SAFETY: If the name exists in BOTH active and disabled keys,
            # it means a previous disable operation failed to delete the
            # active entry. We ignore it here to prevent "ghost" entries
            # from appearing in the disabled list.
            if name in active_names:
                continue
            entries.append({"type": "reg", "name": name, "command": str(value),
                            "source": "Desactivadas", "hive": dhive, "subkey": dsubkey,
                            "enabled": False})
                            
    # 2. Disabled files in startup folders.
    for folder in STARTUP_FOLDERS:
        if os.path.isdir(folder):
            for fname in os.listdir(folder):
                if fname.endswith(".disabled"):
                    original = os.path.splitext(fname)[0]
                    entries.append({"type": "file", "name": original, "command": "",
                                    "source": "Desactivadas", "folder": folder,
                                    "filename": fname, "enabled": False})
    return entries


def _reg_transfer(hive_src, subkey_src, hive_dst, subkey_dst, name, value):
    """Move a registry value from one key to another, rolling back on
    failure.

    The write to the destination is preceded by a read of any previous
    destination value; if deleting the source entry fails, the
    destination is restored exactly as it was (or the fresh value
    removed), so a failure can never leave the entry duplicated on both
    keys. Returns nothing; raises OSError on failure.

    Args:
        hive_src: Source registry hive.
        subkey_src: Source subkey path.
        hive_dst: Destination registry hive.
        subkey_dst: Destination subkey path.
        name: The name of the value to move.
        value: The data to write to the destination.

    Raises:
        OSError: If the transfer cannot be completed.
    """
    prev = None
    prev_type = winreg.REG_SZ
    
    # Step 1: Write to destination, remembering any previous value there.
    with winreg.CreateKey(hive_dst, subkey_dst) as kdst:
        with contextlib.suppress(OSError):
            prev, prev_type = winreg.QueryValueEx(kdst, name)
        winreg.SetValueEx(kdst, name, 0, winreg.REG_SZ, str(value))
        
    # Step 2: Delete from source.
    try:
        with winreg.OpenKey(hive_src, subkey_src, 0, winreg.KEY_SET_VALUE) as ksrc:
            winreg.DeleteValue(ksrc, name)
    except OSError:
        # ROLLBACK: Source deletion failed. Restore destination to its
        # previous state (or delete the fresh value if there was none).
        with winreg.OpenKey(hive_dst, subkey_dst, 0, winreg.KEY_SET_VALUE) as kdst:
            if prev is not None:
                winreg.SetValueEx(kdst, name, 0, prev_type, prev)
            else:
                with contextlib.suppress(OSError):
                    winreg.DeleteValue(kdst, name)
        raise


def is_runonce_entry(entry: dict) -> bool:
    """True when the entry lives in a RunOnce key (execution-once semantics).

    RunOnce entries are meant to run exactly once and then Windows deletes
    them. Disabling them may prevent a one-time task (installer finish,
    first-run setup) from ever executing.

    Args:
        entry: The startup entry dictionary.

    Returns:
        bool: True if the entry is in a RunOnce key.
    """
    subkey = entry.get("subkey", "")
    return "RunOnce" in subkey


def set_startup(entry, enable):
    """Enable/disable a startup entry. Returns (ok, msg).

    Registry toggling moves the value between the active key and its
    *Disabled counterpart through _reg_transfer, which rolls the
    destination back if the source deletion fails: the entry is never
    left duplicated on both keys. Run and RunOnce keys are both handled
    through the same atomic move.

    RunOnce entries (P1-11) are flagged in the message so the UI can
    show a stronger warning before disabling them.

    Args:
        entry: The startup entry dictionary (from get_startup_apps or
               get_disabled_startup).
        enable: True to enable, False to disable.

    Returns:
        tuple: (success: bool, message: str).
    """
    try:
        if entry["type"] == "reg":
            hive, subkey = entry["hive"], entry["subkey"]
            if enable:
                # Move from RunDisabled back to Run.
                d_hive, d_subkey = RUN_KEY_TO_DISABLED.get((hive, subkey), (hive, subkey))
                value = _read_reg_value(d_hive, d_subkey, entry["name"])
                if value is None:
                    return False, "the disabled entry was not found"
                _reg_transfer(d_hive, d_subkey, hive, subkey, entry["name"], value)
            else:
                # Move from Run to RunDisabled.
                value = _read_reg_value(hive, subkey, entry["name"])
                if value is None:
                    return False, "the entry no longer exists"
                d_hive, d_subkey = RUN_KEY_TO_DISABLED.get((hive, subkey), (hive, subkey))
                _reg_transfer(hive, subkey, d_hive, d_subkey, entry["name"], value)
                
            # Flag RunOnce entries so the UI can show a warning
            if is_runonce_entry(entry):
                return True, "OK (RunOnce)"
            return True, "OK"
        else:
            # Folder entry: rename with a .disabled extension.
            folder = entry["folder"]
            if enable:
                src = os.path.join(folder, entry.get("filename", entry["name"] + ".disabled"))
                dst = os.path.join(folder, entry["name"])
                if not os.path.exists(src):
                    return False, "the disabled file no longer exists"
                os.rename(src, dst)
            else:
                src = os.path.join(folder, entry["name"])
                if not os.path.exists(src):
                    return False, "the file no longer exists"
                os.rename(src, src + ".disabled")
            return True, "OK (file)"
    except Exception as e:
        return False, str(e)
