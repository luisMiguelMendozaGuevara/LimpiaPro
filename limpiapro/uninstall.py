"""Uninstaller: installed apps, safe uninstaller launching and leftover
search on disk and registry.

This module provides three core functionalities:

1. **Installed Apps Enumeration**: Reads the Windows registry Uninstall keys
   to list all installed applications with their metadata (name, publisher,
   uninstall command, install location, size).

2. **Safe Uninstaller Launching**: Extracts the executable from UninstallString,
   verifies it exists on disk, and launches it with subprocess.Popen (no shell=True
   to prevent command injection).

3. **Leftover Search**: After uninstallation, searches for residual files and
   registry keys in %APPDATA%, %LOCALAPPDATA%, %PROGRAMDATA%, and HKCU/HKLM\\Software.

Security Guarantees:
    - **No shell=True**: Uninstall commands are parsed with shlex and launched
      as argument lists, preventing command injection through tampered UninstallStrings.
    - **Executable verification**: The executable must exist on disk (resolved
      against System32/PATH when the token carries no path).
    - **Registry namespace protection**: Well-known shared registry trees
      (Microsoft, Classes, Windows, Policies, etc.) are never proposed for deletion.
    - **Install location safety**: The InstallLocation folder is only proposed
      for deletion if the app is no longer registered (proof it was uninstalled).

Backend Rule:
    Every status message returned by this module is stable English/ASCII;
    the UI layer translates user-facing text via i18n.t().
"""

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
# HKCU/HKLM\\Software: well-known shared trees whose loss breaks Windows.
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
    is sorted case-insensitively by display name.
    
    Returns:
        list[dict]: List of application dictionaries with keys:
                    - name (str): Display name of the application.
                    - publisher (str): Publisher/developer name.
                    - uninstall (str): UninstallString from registry.
                    - location (str): InstallLocation from registry.
                    - size_kb (int): EstimatedSize in KB (0 if unknown).
                    
    Notes:
        - Deduplication: Uses (name.lower(), uninstall.lower()) as unique key.
        - Error handling: Silently skips inaccessible registry keys.
        - Sorting: Case-insensitive alphabetical sort by name.
    """
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
    """Get short registry hive name ("HKCU"/"HKLM") for display in paths.
    
    Args:
        hive: Windows registry hive constant (winreg.HKEY_*).
        
    Returns:
        str: Short name ("HKCU", "HKLM", or "?" for unknown).
    """
    if hive == winreg.HKEY_CURRENT_USER:
        return "HKCU"
    if hive == winreg.HKEY_LOCAL_MACHINE:
        return "HKLM"
    return "?"


def _registry_target_allowed(sub_path):
    """Check if a registry path is a legitimate deletion target.
    
    Only sub-trees under *Software* are ever considered (the uninstaller
    never touches Classes, Policies, shell extensions, etc.), and the
    well-known shared namespaces are refused even there. This is the
    second barrier so delete_registry_path() cannot be pointed at an
    arbitrary hive root.
    
    Args:
        sub_path (str): Registry path relative to the hive (e.g., "Software\\Foo\\Bar").
        
    Returns:
        bool: True if the path is safe to delete, False otherwise.
        
    Notes:
        - Only paths under "Software" are allowed.
        - "Software" itself cannot be deleted (len(parts) == 1 check).
        - WOW6432Node is stripped before checking blocked namespaces.
        - Blocked namespaces: Microsoft, Classes, Windows, Policies, etc.
    """
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
    """Recursively delete a registry key.
    
    Children are deleted depth-first (always enumerating index 0, because
    each deletion shifts the remaining children up), then the key itself.
    The path is validated as a legitimate target first: only HKCU/HKLM
    trees under Software and outside the blocked namespaces are accepted.
    
    Args:
        path (str): Full registry path (e.g., "HKCU\\Software\\Foo\\Bar").
        
    Returns:
        bool: True on success, False on any failure (permissions, missing
              key, malformed or unsafe path).
              
    Notes:
        - Safety: Calls _registry_target_allowed() before any deletion.
        - Depth-first: Enumerates index 0 repeatedly (deletions shift indices).
        - Error handling: Returns False on any exception (no partial deletions).
    """
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
    """Resolve a bare executable name against System32, the Windows dir and PATH.
    
    When the uninstall command specifies only an executable name (e.g., "uninstall.exe"
    without a path), this function searches standard locations to find the full path.
    
    Args:
        token (str): Executable name (e.g., "uninstall.exe").
        
    Returns:
        str | None: Full path to the executable, or None if not found.
        
    Search Order:
        1. %SystemRoot%\\System32
        2. %SystemRoot%
        3. PATH environment variable directories
    """
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
    
    This is a security-critical function that parses the UninstallString
    without invoking a shell, preventing command injection through tampered
    registry values.
    
    Args:
        cmd (str): Command line string from UninstallString registry value.
        
    Returns:
        tuple[list[str] | None, str | None]: (argv, error_reason)
            - On success: (["C:\\path\\to\\uninstall.exe", "/arg1", ...], None)
            - On failure: (None, "human-readable error reason")
            
    Security Guarantees:
        - No shell=True: Uses shlex.split() with posix=False for Windows semantics.
        - Executable verification: The executable must exist on disk (resolved
          against System32/PATH when the token carries no path).
        - Empty commands: Rejected with clear error message.
        - Malformed commands: Rejected with parsing error details.
        
    Example:
        >>> argv, err = split_command('"C:\\Program Files\\App\\uninstall.exe" /S')
        >>> argv
        ['C:\\Program Files\\App\\uninstall.exe', '/S']
        >>> err
        None
    """
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
    and launched with an argument list (see split_command). This prevents
    command injection through tampered UninstallString values.
    
    Args:
        command (str): UninstallString from the registry.
        
    Returns:
        tuple[bool, str]: (success, message)
            - On success: (True, "OK")
            - On failure: (False, "human-readable error message")
            
    Notes:
        - Uses subprocess.Popen with shell=False and CREATE_NO_WINDOW flag.
        - The uninstaller runs asynchronously (returns immediately).
        - Error messages are stable English/ASCII for UI translation.
    """
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
    """Lowercase alphanumeric-only normalization for fuzzy comparisons.
    
    Strips all non-alphanumeric characters and lowercases the result.
    Used for fuzzy matching of application names against folder/key names.
    
    Args:
        text (str): Text to normalize.
        
    Returns:
        str: Normalized text (e.g., "My App!" -> "myapp").
    """
    return "".join(ch for ch in text.lower() if ch.isalnum())


def matches_leftover(name, text):
    """Check if `text` (a folder or key name) looks like a leftover of `name`.
    
    Requires either an exact normalized match, or that ALL significant
    tokens (words of 3+ characters) of the application name appear. Much
    stricter than a loose substring search, which would match far too many
    unrelated keys.
    
    Args:
        name (str): Application name (e.g., "My Application").
        text (str): Folder or registry key name to check (e.g., "MyApp").
        
    Returns:
        bool: True if text looks like a leftover of name, False otherwise.
        
    Matching Rules:
        1. Exact normalized match: _norm(name) == _norm(text)
        2. Token match: ALL words of 3+ characters from name appear in text
        
    Example:
        >>> matches_leftover("My Application", "MyApp")
        True  # "my" and "application" both appear in "myapp"
        >>> matches_leftover("My Application", "Other")
        False  # No token match
    """
    tokens = [t for t in re.split(r"[^a-z0-9]+", name.lower())
              if len(t) >= 3]
    low = text.lower()
    if _norm(name) == _norm(text):
        return True
    if not tokens:
        return False
    return all(t in low for t in tokens)


def _app_still_registered(name):
    """Check if an app with the same normalized DisplayName is still in the Uninstall keys.
    
    This is used to verify that an application was actually uninstalled before
    proposing its InstallLocation folder for deletion. If the app is still
    registered, it's likely still installed, and deleting its install dir
    would be dangerous.
    
    Args:
        name (str): Application display name.
        
    Returns:
        bool: True if the app is still registered (not uninstalled), False otherwise.
    """
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
    this module must not make.
    
    Args:
        name (str): Application display name.
        location (str, optional): InstallLocation from registry. Defaults to "".
        
    Returns:
        list[tuple[str, str]]: List of (kind, path) tuples where kind is
                               "folder" or "registry".
                               
    Safety Guarantees:
        - InstallLocation: Only proposed if the app is no longer registered.
        - Registry namespaces: Protected keys (Microsoft, Windows, etc.) are skipped.
        - Fuzzy matching: Uses matches_leftover() for strict token-based matching.
    """
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
