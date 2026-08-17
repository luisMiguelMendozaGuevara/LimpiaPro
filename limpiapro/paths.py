"""Per-user and shared application directories.

Caches, logs and user configuration must NOT live next to the executable:
a normal user cannot write into "C:\\Program Files", so writes would fail
silently and every user of a shared install would mix their data. The app
directory (app_dir) keeps only static resources (winapp2.ini).

  - user data (cache, logs, settings): %LOCALAPPDATA%\\LimpiaPro
  - shared data (global winapp2 rules): %ProgramData%\\LimpiaPro
"""

import os


def get_user_data_dir() -> str:
    """Per-user writable directory for cache, logs and settings.

    Falls back to the user home when LOCALAPPDATA is undefined. The
    directory is created on first use."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    data_dir = os.path.join(base, "LimpiaPro")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        pass
    return data_dir


def get_shared_data_dir() -> str:
    """Machine-wide directory for shared resources (winapp2.ini)."""
    base = os.environ.get("ProgramData", r"C:\ProgramData")
    data_dir = os.path.join(base, "LimpiaPro")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError:
        pass
    return data_dir


def get_logs_dir() -> str:
    """Writable directory for the error log."""
    logs_dir = os.path.join(get_user_data_dir(), "logs")
    try:
        os.makedirs(logs_dir, exist_ok=True)
    except OSError:
        pass
    return logs_dir


def get_cache_file() -> str:
    """Path of the scan results cache (under the user data dir)."""
    return os.path.join(get_user_data_dir(), "limpiador_cache.json")