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


def set_startup(entry, enable):
    """Enable/disable a startup entry. Returns (ok, msg).

    Registry toggling is a two-step move (write to the target key, delete
    from the source one); it is not transactional -- a failure mid-way can
    leave the value on both keys, which get_disabled_startup filters out
    on the next read."""
    try:
        if entry["type"] == "reg":
            hive, subkey = entry["hive"], entry["subkey"]
            if enable:
                # Move from RunDisabled back to Run.
                d_hive, d_subkey = RUN_KEY_TO_DISABLED.get((hive, subkey), (hive, subkey))
                value = _read_reg_value(d_hive, d_subkey, entry["name"])
                if value is None:
                    return False, "the disabled entry was not found"
                with winreg.CreateKey(hive, subkey) as k:
                    winreg.SetValueEx(k, entry["name"], 0, winreg.REG_SZ, str(value))
                with winreg.OpenKey(d_hive, d_subkey, 0, winreg.KEY_SET_VALUE) as k:
                    try:
                        winreg.DeleteValue(k, entry["name"])
                    except OSError:
                        pass
            else:
                value = _read_reg_value(hive, subkey, entry["name"])
                if value is None:
                    return False, "the entry no longer exists"
                d_hive, d_subkey = RUN_KEY_TO_DISABLED.get((hive, subkey))
                with winreg.CreateKey(d_hive, d_subkey) as k:
                    winreg.SetValueEx(k, entry["name"], 0, winreg.REG_SZ, str(value))
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, entry["name"])
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
            return True, "OK"
    except Exception as e:
        return False, str(e)
