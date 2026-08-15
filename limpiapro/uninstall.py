"""Desinstalador: apps instaladas, lanzamiento seguro de desinstaladores y
busqueda de restos en disco y registro."""

import os
import re
import shlex
import subprocess
import winreg

# Claves de sistema que nunca se proponen para borrar como "restos": son
# too genericas y borrarlas romperia Windows u otras aplicaciones.
_PROTECTED_KEY_NAMES = {
    "microsoft", "classes", "windows", "policies", "wow6432node",
    "currentversion", "commonfiles", "programfiles", "programfilesx86",
    "clients", "registeredapplications", "odbc", "explorer", "windowsnt",
    "squirreltemp", "temp",
}


def get_installed_apps():
    """Aplicaciones instaladas desde las claves Uninstall del registro."""
    apps = []
    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    seen = set()
    for hive, base in roots:
        try:
            key = winreg.OpenKey(hive, base)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(key)[0]):
            try:
                sub = winreg.EnumKey(key, i)
                with winreg.OpenKey(key, sub) as skey:
                    def _get(name):
                        try:
                            val, _ = winreg.QueryValueEx(skey, name)
                            return val
                        except OSError:
                            return ""
                    display = _get("DisplayName")
                    if not display:
                        continue
                    est = _get("EstimatedSize")
                    size_kb = 0
                    if est:
                        try:
                            size_kb = int(est)
                        except (TypeError, ValueError):
                            pass
                    entry = {
                        "name": str(display).strip(),
                        "publisher": str(_get("DisplayPublisher") or "").strip(),
                        "uninstall": str(_get("UninstallString") or "").strip(),
                        "location": str(_get("InstallLocation") or "").strip(),
                        "size_kb": size_kb,
                    }
                    keyid = (entry["name"].lower(), entry["uninstall"].lower())
                    if keyid in seen:
                        continue
                    seen.add(keyid)
                    apps.append(entry)
            except OSError:
                continue
        winreg.CloseKey(key)
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def _hive_name(hive):
    if hive == winreg.HKEY_CURRENT_USER:
        return "HKCU"
    if hive == winreg.HKEY_LOCAL_MACHINE:
        return "HKLM"
    return "?"


def delete_registry_path(path):
    """Elimina una clave de registro recursivamente. path: 'HKCU\\Software\\Foo'."""
    try:
        hive_name, sub = path.split("\\", 1)
        hive = (winreg.HKEY_CURRENT_USER if hive_name.upper() == "HKCU"
                else winreg.HKEY_LOCAL_MACHINE)

        def _rec(h, key_path):
            with winreg.OpenKey(h, key_path, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
                for _ in range(winreg.QueryInfoKey(k)[0]):
                    try:
                        child = winreg.EnumKey(k, 0)
                    except OSError:
                        break
                    _rec(k, child)
            winreg.DeleteKey(h, key_path)

        _rec(hive, sub)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# Lanzamiento seguro de desinstaladores
# --------------------------------------------------------------------------

def _resolve_exe(token):
    """Resuelve un ejecutable por nombre contra System32 y el PATH.
    Devuelve la ruta completa o None."""
    for base in (os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                              "System32"),
                 os.path.join(os.environ.get("SystemRoot", r"C:\Windows"))):
        cand = os.path.join(base, token)
        if os.path.isfile(cand):
            return cand
    for d in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(d.strip('"'), token)
        if os.path.isfile(cand):
            return cand
    return None


def split_command(cmd):
    """Divide una linea de comandos en [exe, *args] sin usar shell.

    Devuelve (argv, None) o (None, motivo). El ejecutable debe existir en
    disco (resuelto contra System32/PATH si va sin ruta); si no, no se
    ejecuta nada. Evita la inyeccion de comandos por UninstallString."""
    cmd = os.path.expandvars((cmd or "").strip())
    if not cmd:
        return None, "el comando de desinstalacion esta vacio"
    try:
        tokens = [t.strip('"') for t in shlex.split(cmd, posix=False)]
    except ValueError as e:
        return None, f"no se pudo interpretar el comando ({e})"
    tokens = [t for t in tokens if t]
    if not tokens:
        return None, "el comando de desinstalacion esta vacio"
    exe = tokens[0]
    if os.path.sep in exe:
        if not os.path.isfile(exe):
            return None, f"el ejecutable no existe: {exe}"
    else:
        resolved = _resolve_exe(exe)
        if not resolved:
            return None, f"no se encontro el ejecutable: {exe}"
        exe = resolved
    return [exe] + tokens[1:], None


def launch_uninstaller(command):
    """Lanza un UninstallString del registro de forma segura.

    Nunca usa shell=True: el ejecutable se extrae, se verifica y se lanza
    con una lista de argumentos. Devuelve (ok, msg)."""
    argv, err = split_command(command)
    if argv is None:
        return False, err
    try:
        subprocess.Popen(argv, shell=False,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return True, "OK"
    except OSError as e:
        return False, str(e)


# --------------------------------------------------------------------------
# Busqueda de restos
# --------------------------------------------------------------------------

def _norm(text):
    return "".join(ch for ch in text.lower() if ch.isalnum())


def matches_leftover(name, text):
    """True si `text` (nombre de carpeta o clave) parece un resto de `name`.

    Exige match exacto normalizado, o que TODOS los tokens significativos
    (palabras de 3+ caracteres) del nombre aparezcan. Mucho mas estricto
    que una busqueda por subcadenas sueltas."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", name.lower())
              if len(t) >= 3]
    low = text.lower()
    if _norm(name) == _norm(text):
        return True
    if not tokens:
        return False
    return all(t in low for t in tokens)


def find_leftovers(name, location=""):
    """Busca restos de un programa en disco y registro. Devuelve [(tipo, ruta)]."""
    leftovers = []
    if not name:
        return leftovers

    if location and os.path.exists(location):
        leftovers.append(("carpeta", location))
    for base in (os.path.expandvars(r"%APPDATA%"), os.path.expandvars(r"%LOCALAPPDATA%"),
                 os.path.expandvars(r"%PROGRAMDATA%")):
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.listdir(base):
                p = os.path.join(base, entry)
                if os.path.isdir(p) and matches_leftover(name, entry):
                    leftovers.append(("carpeta", p))
        except OSError:
            pass
    bases = [
        (winreg.HKEY_CURRENT_USER, r"Software"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node"),
    ]
    for hive, base in bases:
        try:
            key = winreg.OpenKey(hive, base)
        except OSError:
            continue
        for i in range(winreg.QueryInfoKey(key)[0]):
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            if _norm(sub) in _PROTECTED_KEY_NAMES:
                continue
            if matches_leftover(name, sub):
                leftovers.append(("registro", f"{_hive_name(hive)}\\{base}\\{sub}"))
        winreg.CloseKey(key)
    return leftovers
