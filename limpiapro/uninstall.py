"""Uninstaller: installed apps, safe uninstaller launching and leftover
search on disk and registry.

Backend rule: every status message returned by this module is stable
English/ASCII; the UI layer translates user-facing text via i18n.t()."""

import os
import re
import shlex
import subprocess
import winreg

# System key names that are never proposed for deletion as "leftovers":
# they are too generic and removing them would break Windows or other
# applications.
_PROTECTED_KEY_NAMES = {
    "microsoft", "classes", "windows", "policies", "wow6432node",
    "currentversion", "commonfiles", "programfiles", "programfilesx86",
    "clients", "registeredapplications", "odbc", "explorer", "windowsnt",
    "squirreltemp", "temp",
}

# Registry namespaces that must never be deleted even under
# HKCU/HKLM\Software: well-known shared trees whose loss breaks Windows.
_BLOCKED_REGISTRY_NAMESPACES = {
    "microsoft", "classes", "windows", "policies", "clients",
    "registeredapplications", "odbc", "explorer", "commonfiles",
    "programfiles", "shell", "class", "installer", "event",
    "help", "fonts", "schemes", "tools", "types",
}


def get_installed_apps():
    """List installed applications from the registry Uninstall keys.

    Walks the three standard roots (HKLM, HKLM WOW6432Node, HKCU), reads
    DisplayName/DisplayPublisher/UninstallString/InstallLocation/
    EstimatedSize and deduplicates by (name, uninstall command). The result
    is sorted case-insensitively by display name."""
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
    """Short registry hive name ("HKCU"/"HKLM") for display in paths."""
    if hive == winreg.HKEY_CURRENT_USER:
        return "HKCU"
    if hive == winreg.HKEY_LOCAL_MACHINE:
        return "HKLM"
    return "?"


def _registry_target_allowed(sub_path):
    """True when a registry path is a legitimate deletion target.

    Only sub-trees under *Software* are ever considered (the uninstaller
    never touches Classes, Policies, shell extensions, etc.), and the
    well-known shared namespaces are refused even there. This is the
    second barrier so delete_registry_path() cannot be pointed at an
    arbitrary hive root."""
    parts = [p.lower() for p in sub_path.replace("/", "\\").split("\\")
             if p.strip()]
    if not parts or parts[0] != "software":
        return False
    if len(parts) == 1:
        return False  # never delete Software itself
    body = parts[1:]
    if body[0] == "wow6432node":
        body = body[1:]
        if not body:
            return False
    for p in body:
        if p in _BLOCKED_REGISTRY_NAMESPACES:
            return False
    return True


def delete_registry_path(path):
    """Recursively delete a registry key. path: 'HKCU\\Software\\Foo'.

    Children are deleted depth-first (always enumerating index 0, because
    each deletion shifts the remaining children up), then the key itself.
    The path is validated as a legitimate target first: only HKCU/HKLM
    trees under Software and outside the blocked namespaces are accepted.
    Returns True on success, False on any failure (permissions, missing
    key, malformed or unsafe path)."""
    try:
        hive_name, sub = path.split("\\", 1)
        hive = (winreg.HKEY_CURRENT_USER if hive_name.upper() == "HKCU"
                else winreg.HKEY_LOCAL_MACHINE)
        if not _registry_target_allowed(sub):
            return False

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
# Safe uninstaller launching
# --------------------------------------------------------------------------

def _resolve_exe(token):
    """Resolve a bare executable name against System32, the Windows dir and
    PATH. Returns the full path, or None when it cannot be found."""
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
    """Split a command line into [exe, *args] without using a shell.

    Returns (argv, None) on success or (None, reason) on failure. The
    executable must exist on disk (resolved against System32/PATH when the
    token carries no path); otherwise nothing gets executed. This blocks
    command injection through a tampered UninstallString."""
    cmd = os.path.expandvars((cmd or "").strip())
    if not cmd:
        return None, "the uninstall command is empty"
    try:
        tokens = [t.strip('"') for t in shlex.split(cmd, posix=False)]
    except ValueError as e:
        return None, f"could not parse the command ({e})"
    tokens = [t for t in tokens if t]
    if not tokens:
        return None, "the uninstall command is empty"
    exe = tokens[0]
    if os.path.sep in exe:
        if not os.path.isfile(exe):
            return None, f"the executable does not exist: {exe}"
    else:
        resolved = _resolve_exe(exe)
        if not resolved:
            return None, f"the executable was not found: {exe}"
        exe = resolved
    return [exe] + tokens[1:], None


def launch_uninstaller(command):
    """Safely launch a registry UninstallString.

    Never uses shell=True: the executable is extracted, verified to exist
    and launched with an argument list (see split_command). Returns
    (ok, msg) where msg is a stable English status/detail string."""
    argv, err = split_command(command)
    if argv is None:
        return False, err
    try:
        subprocess.Popen(argv, shell=False,  # nosec B603 - arg list, no shell
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return True, "OK"
    except OSError as e:
        return False, str(e)


# --------------------------------------------------------------------------
# Leftover search
# --------------------------------------------------------------------------

def _norm(text):
    """Lowercase alphanumeric-only normalization for fuzzy comparisons."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def matches_leftover(name, text):
    """True if `text` (a folder or key name) looks like a leftover of `name`.

    Requires either an exact normalized match, or that ALL significant
    tokens (words of 3+ characters) of the application name appear. Much
    stricter than a loose substring search, which would match far too many
    unrelated keys."""
    tokens = [t for t in re.split(r"[^a-z0-9]+", name.lower())
              if len(t) >= 3]
    low = text.lower()
    if _norm(name) == _norm(text):
        return True
    if not tokens:
        return False
    return all(t in low for t in tokens)


def _app_still_registered(name):
    """True when an app with the same normalized DisplayName is still in the
    Uninstall keys (i.e. it was NOT actually uninstalled)."""
    target = _norm(name)
    if not target:
        return False
    for app in get_installed_apps():
        if _norm(app["name"]) == target:
            return True
    return False


def find_leftovers(name, location=""):
    """Search disk and registry for leftovers of a program.

    Returns a list of (kind, path) tuples where kind is the stable English
    tag "folder" or "registry" (translated for display by the UI). Scans
    the install location, %APPDATA%, %LOCALAPPDATA%, %PROGRAMDATA% and the
    Software keys of HKCU/HKLM (including WOW6432Node), skipping the
    protected generic key names.

    The InstallLocation folder is only offered when the application is no
    longer present in the Uninstall registry (proof it was uninstalled):
    blindly proposing a live install dir for whole deletion is the risk
    this module must not make."""
    leftovers = []
    if not name:
        return leftovers

    if location and os.path.exists(location) and not _app_still_registered(name):
        leftovers.append(("folder", location))
    for base in (os.path.expandvars(r"%APPDATA%"), os.path.expandvars(r"%LOCALAPPDATA%"),
                 os.path.expandvars(r"%PROGRAMDATA%")):
        if not os.path.isdir(base):
            continue
        try:
            for entry in os.listdir(base):
                p = os.path.join(base, entry)
                if os.path.isdir(p) and matches_leftover(name, entry):
                    leftovers.append(("folder", p))
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
                leftovers.append(("registry", f"{_hive_name(hive)}\\{base}\\{sub}"))
        winreg.CloseKey(key)
    return leftovers
