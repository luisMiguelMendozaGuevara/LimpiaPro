"""Per-user and shared application directories.

This module manages the filesystem layout for application data, following
Windows best practices for per-user and shared resources.

Architecture Rationale:
    Caches, logs and user configuration must NOT live next to the executable:
    a normal user cannot write into "C:\\Program Files", so writes would fail
    silently and every user of a shared install would mix their data. The app
    directory (app_dir in utils.py) keeps only static resources (winapp2.ini).

Directory Layout:
    - **User data** (cache, logs, settings): %LOCALAPPDATA%\\LimpiaPro
      This is per-user, writable, and isolated between users on the same machine.
    - **Shared data** (global winapp2 rules): %ProgramData%\\LimpiaPro
      This is machine-wide and accessible to all users.

Functions:
    - get_user_data_dir(): Per-user writable directory for cache, logs, settings.
    - get_shared_data_dir(): Machine-wide directory for shared resources.
    - get_logs_dir(): Writable directory for the error log (under user data).
    - get_cache_file(): Path of the scan results cache (under user data).
"""

import contextlib
import os


def get_user_data_dir() -> str:
    """Get the per-user writable directory for cache, logs and settings.
    
    Falls back to the user home when LOCALAPPDATA is undefined (non-Windows
    or restricted environment). The directory is created on first use with
    os.makedirs(exist_ok=True).
    
    Returns:
        str: Absolute path to the per-user data directory.
             Example: "C:\\Users\\John\\AppData\\Local\\LimpiaPro"
             
    Notes:
        - Uses %LOCALAPPDATA% (e.g., C:\\Users\\John\\AppData\\Local).
        - LIMPIAPRO_DATA_DIR overrides the location entirely: the test suite
          points it at a temp dir so no test can ever touch (or pollute) the
          real user cache/logs/settings.
        - Fallback: os.path.expanduser("~") if LOCALAPPDATA is undefined.
        - Directory creation: Silently ignores OSError if creation fails
          (e.g., permission denied, read-only filesystem).
    """
    override = os.environ.get("LIMPIAPRO_DATA_DIR")
    base = override or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    data_dir = base if override else os.path.join(base, "LimpiaPro")
    with contextlib.suppress(OSError):
        os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_shared_data_dir() -> str:
    """Get the machine-wide directory for shared resources (winapp2.ini).
    
    This directory is accessible to all users on the machine and is used
    for shared resources like the global winapp2.ini database.
    
    Returns:
        str: Absolute path to the shared data directory.
             Example: "C:\\ProgramData\\LimpiaPro"
             
    Notes:
        - Uses %ProgramData% (e.g., C:\\ProgramData).
        - Fallback: "C:\\ProgramData" if ProgramData is undefined.
        - Directory creation: Silently ignores OSError if creation fails.
    """
    base = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    data_dir = os.path.join(base, "LimpiaPro")
    with contextlib.suppress(OSError):
        os.makedirs(data_dir, exist_ok=True)
    return data_dir


def get_logs_dir() -> str:
    """Get the writable directory for the error log.
    
    This is a subdirectory of the user data directory, ensuring logs are
    per-user and writable.
    
    Returns:
        str: Absolute path to the logs directory.
             Example: "C:\\Users\\John\\AppData\\Local\\LimpiaPro\\logs"
             
    Notes:
        - Located under get_user_data_dir() / "logs".
        - Directory creation: Silently ignores OSError if creation fails.
        - Used by utils._errlog() and audit_log.AuditLogger.
    """
    logs_dir = os.path.join(get_user_data_dir(), "logs")
    with contextlib.suppress(OSError):
        os.makedirs(logs_dir, exist_ok=True)
    return logs_dir


def get_cache_file() -> str:
    """Get the path of the scan results cache (under the user data dir).
    
    This file stores the results of the last system scan (size and file count
    per category) to enable instant startup on subsequent launches.
    
    Returns:
        str: Absolute path to the cache file.
             Example: "C:\\Users\\John\\AppData\\Local\\LimpiaPro\\limpiador_cache.json"
             
    Notes:
        - Format: JSON with schema versioning (see CacheService in services/).
        - Used by controller.py (LimpiaProController) to locate the analysis
          cache consumed by the incremental startup (Lote B1).
    """
    return os.path.join(get_user_data_dir(), "limpiador_cache.json")
