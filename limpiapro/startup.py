"""Apps de inicio (registro Run/RunOnce + carpetas de inicio)."""

import os
import winreg

RUN_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "Usuario (HKCU Run)"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "Usuario (HKCU RunOnce)"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "Sistema (HKLM Run)"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "Sistema (HKLM RunOnce)"),
]

STARTUP_FOLDERS = [
    os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"),
    os.path.expandvars(r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\StartUp"),
]

# La clave "Disabled" respalda los valores que el usuario desactiva
RUN_KEYS_DISABLED = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunDisabled", "Usuario (desactivadas)"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnceDisabled", "Usuario (desactivadas)"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunDisabled", "Sistema (desactivadas)"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnceDisabled", "Sistema (desactivadas)"),
]

# Mapa: (hive, clave_activa) -> (hive, clave_desactivadas)
RUN_KEY_TO_DISABLED = {
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"):
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunDisabled"),
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"):
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnceDisabled"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"):
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunDisabled"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"):
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnceDisabled"),
}


def _read_reg_entries(hive, subkey):
    """Devuelve {nombre: valor} de una clave de registro."""
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


def get_startup_apps():
    """Lista de aplicaciones de inicio activas."""
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
    """Aplicaciones que el usuario ha desactivado (para poder reactivarlas)."""
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
    """Activa/desactiva una entrada de inicio. Devuelve (ok, msg)."""
    try:
        if entry["type"] == "reg":
            hive, subkey = entry["hive"], entry["subkey"]
            if enable:
                # mover de RunDisabled de vuelta a Run
                target = RUN_KEY_TO_DISABLED.get((hive, subkey), (hive, subkey))
                d_hive, d_subkey = target
                value = _read_reg_entries(d_hive, d_subkey).get(entry["name"])
                if value is None:
                    return False, "No se encontro la entrada desactivada."
                with winreg.CreateKey(hive, subkey) as k:
                    winreg.SetValueEx(k, entry["name"], 0, winreg.REG_SZ, str(value))
                with winreg.OpenKey(d_hive, d_subkey, 0, winreg.KEY_SET_VALUE) as k:
                    try:
                        winreg.DeleteValue(k, entry["name"])
                    except OSError:
                        pass
            else:
                value = _read_reg_entries(hive, subkey).get(entry["name"])
                if value is None:
                    return False, "La entrada ya no existe."
                target = RUN_KEY_TO_DISABLED.get((hive, subkey))
                d_hive, d_subkey = target
                with winreg.CreateKey(d_hive, d_subkey) as k:
                    winreg.SetValueEx(k, entry["name"], 0, winreg.REG_SZ, str(value))
                with winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, entry["name"])
            return True, "OK"
        else:
            # entrada de carpeta: renombrar con extension .disabled
            folder = entry["folder"]
            if enable:
                src = os.path.join(folder, entry.get("filename", entry["name"] + ".disabled"))
                dst = os.path.join(folder, entry["name"])
                if not os.path.exists(src):
                    return False, "El archivo desactivado ya no existe."
                os.rename(src, dst)
            else:
                src = os.path.join(folder, entry["name"])
                if not os.path.exists(src):
                    return False, "El archivo ya no existe."
                os.rename(src, src + ".disabled")
            return True, "OK"
    except Exception as e:
        return False, str(e)
