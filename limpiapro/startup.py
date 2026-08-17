"""Startup applications (Run/RunOnce registry keys + startup folders).

Disabling a registry entry moves its value to a parallel *Disabled key
(e.g. Run -> RunDisabled) so it can be restored later; disabling a
startup-folder file renames it with a ".disabled" extension."""

import os
import winreg

# Single source list: (hive, active key, disabled key, display label).
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
RUN_KEY_TO_DISABLED = {(h, a): (h, d) for h, a, d, _s in _RUN_PAIRS}

STARTUP_FOLDERS = [
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
    os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\StartUp"),
]


def _read_reg_entries(hive, subkey):
    """All values of a registry key as {name: value} ({} on any error)."""
    out = {}
    try:
        with winreg.OpenKey(hive, subkey) as key:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    out[name] = value
                    i += 1
                except OSError:
                    break
    except OSError:
        pass
    return out


def _read_reg_value(hive, subkey, name):
    """Read a single value without enumerating the whole key."""
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
    move it back and forth."""
    entries = []
    for hive, subkey, src in RUN_KEYS:
        for name, value in _read_reg_entries(hive, subkey).items():
            entries.append({"type": "reg", "name": name, "command": str(value),
                            "source": src, "hive": hive, "subkey": subkey, "enabled": True})
    for folder in STARTUP_FOLDERS:
        if os.path.isdir(folder):
            for fname in os.listdir(folder):
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
    renamed with a '.disabled' extension."""
    entries = []
    for (hive, subkey), (dhive, dsubkey) in RUN_KEY_TO_DISABLED.items():
        active_names = set(_read_reg_entries(hive, subkey).keys())
        for name, value in _read_reg_entries(dhive, dsubkey).items():
            if name in active_names:
                continue
            entries.append({"type": "reg", "name": name, "command": str(value),
                            "source": "Desactivadas", "hive": dhive, "subkey": dsubkey,
                            "enabled": False})
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
    keys. Returns nothing; raises OSError on failure."""
    prev = None
    prev_type = winreg.REG_SZ
    with winreg.CreateKey(hive_dst, subkey_dst) as kdst:
        try:
            prev, prev_type = winreg.QueryValueEx(kdst, name)
        except OSError:
            pass
        winreg.SetValueEx(kdst, name, 0, winreg.REG_SZ, str(value))
    try:
        with winreg.OpenKey(hive_src, subkey_src, 0, winreg.KEY_SET_VALUE) as ksrc:
            winreg.DeleteValue(ksrc, name)
    except OSError:
        with winreg.OpenKey(hive_dst, subkey_dst, 0, winreg.KEY_SET_VALUE) as kdst:
            if prev is not None:
                winreg.SetValueEx(kdst, name, 0, prev_type, prev)
            else:
                try:
                    winreg.DeleteValue(kdst, name)
                except OSError:
                    pass
        raise


def is_runonce_entry(entry: dict) -> bool:
    """True when the entry lives in a RunOnce key (execution-once semantics).

    RunOnce entries are meant to run exactly once and then Windows deletes
    them. Disabling them may prevent a one-time task (installer finish,
    first-run setup) from ever executing."""
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
    show a stronger warning before disabling them."""
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
