"""Common utilities: paths, formatting, deletion and folder measuring.

This module provides the foundational building blocks for the entire application:

Core Responsibilities:
    - **Filesystem Operations**: Optimized folder scanning (_iter_tree_files,
      _fast_folder_stats) and safe deletion (_delete_measured) using os.scandir
      for cached stat information.
    - **Parallel Execution**: ThreadPoolExecutor wrapper (_parallel_map) for
      concurrent file operations without disk thrashing.
    - **Error Classification**: Structured deletion error reporting (DeleteError)
      with detailed error kinds (in_use, access_denied, not_found, etc.).
    - **Safety Integration**: Re-exports is_safe_delete_target from safety.py
      for backwards compatibility, ensuring all deletion operations pass through
      the central safety policy.
    - **System Utilities**: Admin privilege detection, human-readable size
      formatting, OEM code page handling for Windows console output.

Performance Optimizations:
    - Single-pass traversal: _delete_measured measures and deletes in one walk,
      avoiding the old measure-then-rmtree pattern that scanned twice.
    - Cached DirEntry stats: os.scandir provides is_dir/is_file and stat() without
      extra syscalls, critical for 20k+ file scans.
    - Chunked progress reporting: Updates every N files to avoid UI flooding.

Safety Guarantees:
    - All destructive operations pass through is_safe_delete_target() before
      touching the filesystem (P0-2).
    - Junctions/reparse points are never descended into during walks.
    - Read-only files are made writable before deletion attempts.
    - Symlinks/junctions are removed without following their targets.
"""

import ctypes
import errno
import glob as globmod
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from .paths import get_logs_dir
from .safety import SafetyGuard, is_safe_delete_target  # noqa: F401  (re-export)

# Progress reporting intervals: how many files between notifications.
# Tuned to balance UI responsiveness with performance overhead.
PROGRESS_STATS = 500      # For fast folder stats (scandir-based scans)
PROGRESS_RULES = 100      # For winapp2 rule scanning
PROGRESS_DELETE = 20      # For deletion operations
DEFAULT_WORKERS = 4       # Default thread pool size for parallel operations


# Windows error codes (winerror) used to classify deletion failures.
# These map OSError.winerror values to semantic error kinds.
_WINERROR_IN_USE = 32          # ERROR_SHARING_VIOLATION: file locked by another process
_WINERROR_ACCESS_DENIED = 5    # ERROR_ACCESS_DENIED: insufficient permissions
_WINERROR_NOT_FOUND = 2        # ERROR_FILE_NOT_FOUND: file doesn't exist
_WINERROR_PATH_NOT_FOUND = 3   # ERROR_PATH_NOT_FOUND: directory doesn't exist
_WINERROR_DIR_NOT_EMPTY = 145  # ERROR_DIR_NOT_EMPTY: rmdir on non-empty dir


@dataclass
class DeleteError:
    """One failed deletion with enough detail to diagnose it.
    
    This structured error object captures all relevant information about a
    deletion failure, enabling the UI to report exactly which path failed,
    why it failed, and what type of failure occurred (instead of a bare
    "n errors" counter).
    
    Attributes:
        path (str): Absolute path of the file/folder that failed to delete.
        operation (str): The operation attempted: "remove" | "rmtree" | "rmdir" | "safety".
        kind (str): Semantic error classification from _classify_error():
                    "in_use" | "access_denied" | "not_found" | "readonly" |
                    "dir_not_empty" | "safety" | "other".
        code (int): Windows error code (winerror) when available, else errno. 0 if unknown.
        message (str): Human-readable error message from the exception or custom message.
        
    Example:
        >>> err = DeleteError(
        ...     path="C:\\\\Temp\\\\locked.tmp",
        ...     operation="remove",
        ...     kind="in_use",
        ...     code=32,
        ...     message="[WinError 32] The process cannot access the file"
        ... )
    """
    path: str
    operation: str              # "remove" | "rmtree" | "rmdir" | "safety"
    kind: str                   # see _classify_error kind values
    code: int = 0               # winerror when available, else errno
    message: str = ""


def _winerror(e: OSError) -> int:
    """Extract the preferred error code for diagnostics: winerror, then errno.
    
    Windows OSError exceptions carry both .winerror (Windows-specific code) and
    .errno (POSIX-style code). This function prefers winerror when available,
    as it provides more precise Windows error semantics.
    
    Args:
        e (OSError): The exception to extract the code from.
        
    Returns:
        int: The error code (winerror preferred, errno fallback), or 0 if neither exists.
    """
    return int(getattr(e, "winerror", 0) or e.errno or 0)


def _classify_error(e: OSError) -> str:
    """Classify a deletion OSError into a stable, short kind string.
    
    Maps Windows error codes (winerror) and POSIX errno values to semantic
    error kinds that the UI can use to display meaningful error messages
    and statistics.
    
    Args:
        e (OSError): The exception to classify.
        
    Returns:
        str: One of:
            - "in_use": File is locked by another process (ERROR_SHARING_VIOLATION).
            - "access_denied": Insufficient permissions (ERROR_ACCESS_DENIED, EACCES, EPERM).
            - "not_found": File/directory doesn't exist (ERROR_FILE_NOT_FOUND, ENOENT).
            - "dir_not_empty": Directory is not empty (ERROR_DIR_NOT_EMPTY).
            - "readonly": File is read-only (treated as access_denied).
            - "other": Unclassified error.
            
    Notes:
        - This classification is used by DeleteError.kind for UI reporting.
        - The "readonly" kind is currently mapped to "access_denied" as they
          share the same recovery strategy (make writable and retry).
    """
    code = _winerror(e)
    if code == _WINERROR_IN_USE:
        return "in_use"
    if code == _WINERROR_ACCESS_DENIED:
        return "access_denied"
    if code in (_WINERROR_NOT_FOUND, _WINERROR_PATH_NOT_FOUND):
        return "not_found"
    if code == _WINERROR_DIR_NOT_EMPTY:
        return "dir_not_empty"
    err = int(getattr(e, "errno", 0) or 0)
    if err in (errno.EACCES, errno.EPERM):
        return "access_denied"
    if err == errno.ENOENT:
        return "not_found"
    return "other"


def _make_error(path: str, operation: str, e: OSError | None,
                kind: str | None = None,
                message: str = "") -> DeleteError:
    """Build a DeleteError from an OSError (or a fixed kind, e.g. a safety
    policy rejection where there is no underlying exception).
    
    This factory function standardizes error creation, handling both
    exception-based errors (with automatic classification) and synthetic
    errors (e.g., safety policy rejections with no OSError).
    
    Args:
        path (str): Absolute path of the target.
        operation (str): The operation that failed ("remove", "rmtree", "rmdir", "safety").
        e (OSError | None): The exception that occurred, or None for synthetic errors.
        kind (str | None, optional): Override the automatic error classification.
                                     Used for "safety" errors with no OSError.
        message (str, optional): Custom error message. If empty, uses str(e).
        
    Returns:
        DeleteError: A fully populated DeleteError instance.
        
    Example:
        >>> # From an OSError:
        >>> err = _make_error("C:\\\\Temp\\\\file.tmp", "remove", OSError(13, "Permission denied"))
        >>> # Synthetic safety error:
        >>> err = _make_error("C:\\\\Users\\\\John\\\\Documents", "safety", None, kind="safety", message="refused")
    """
    if kind is None:
        kind = _classify_error(e) if e is not None else "other"
    return DeleteError(path=path, operation=operation, kind=kind,
                       code=_winerror(e) if e is not None else 0,
                       message=message or (str(e) if e is not None else ""))


# --------------------------------------------------------------------------
# Delete safety layer (P0-2): a central policy gate that every destructive
# operation must pass BEFORE touching the filesystem. The policy lives in
# limpiapro.safety (SafetyGuard); is_safe_delete_target is re-exported at
# the top of this module so the historical import path keeps working while
# the gate itself is a single shared object the UI can never bypass.
# --------------------------------------------------------------------------

def is_drive_root(path: str) -> bool:
    """Check if a path is exactly a drive root like 'C:\\\\'.
    
    This is a convenience wrapper around SafetyGuard.is_drive_root() for
    backwards compatibility and ease of use.
    
    Args:
        path (str): The path to check (may contain %ENV% variables).
        
    Returns:
        bool: True if the path is a drive root (e.g., "C:\\\\", "D:/"), False otherwise.
        
    Example:
        >>> is_drive_root("C:\\\\")
        True
        >>> is_drive_root("C:\\\\Windows")
        False
    """
    return SafetyGuard.is_drive_root(path)


def app_dir() -> str:
    """Get the application directory (works packaged with PyInstaller too).
    
    In development, this is the project root: the folder holding limpiador.py,
    winapp2.ini, the cache file, and the error log. When packaged with
    PyInstaller, it's the directory containing the executable.
    
    Returns:
        str: Absolute path to the application directory.
        
    Notes:
        - Detects PyInstaller packaging via sys.frozen flag.
        - Used by paths.py and winapp2.py to locate bundled resources.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """Get the directory holding READ-ONLY bundled data (winapp2.ini, icons).

    PyInstaller >= 6 unpacks spec `datas` into the `_internal` folder for
    OneDir builds and into the extraction dir for one-file builds; both are
    `sys._MEIPASS` at runtime. Looking bundled data up here (instead of
    app_dir()) makes it impossible for the exe to lose its resources by
    moving the folder or by the datas landing next to the exe.

    Returns:
        str: Absolute path to the bundled-data directory.
    """
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", app_dir())
    return app_dir()


def is_admin() -> bool:
    """Check if the process is running with elevated (UAC administrator) privileges.
    
    Uses the Windows shell32.IsUserAnAdmin() API to determine if the current
    process has full administrative rights.
    
    Returns:
        bool: True if running as administrator, False otherwise.
        
    Notes:
        - Returns False on non-Windows platforms or if the API call fails.
        - Used by app_qt.py to trigger UAC elevation if needed.
        - Some categories (temp, apps, winapp) require admin privileges.
    """
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def format_size(num: float) -> str:
    """Convert bytes to a human-readable size string (KB/MB/GB/TB/PB).
    
    Formats a numeric byte count into a human-friendly string with appropriate
    units. Negative values are displayed as "-" to indicate errors or unknowns.
    
    Args:
        num (float): Size in bytes. Can be int or float.
        
    Returns:
        str: Formatted string like "1.5 MB", "512 B", or "-" for negatives.
        
    Example:
        >>> format_size(1024)
        '1.0 KB'
        >>> format_size(1536)
        '1.5 KB'
        >>> format_size(-1)
        '-'
        >>> format_size(500)
        '500 B'
    """
    if isinstance(num, int) and num < 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.1f} PB"


def glob_like(path: str) -> list[str]:
    """Expand glob wildcards in a path, or return the path as-is if no wildcards.
    
    This function checks if the path contains glob wildcards (*, ?, [) and
    expands them using glob.glob(). If no wildcards are present, it returns
    the path in a list without filesystem access (efficient for plain paths).
    
    Args:
        path (str): Path that may contain wildcards (e.g., "C:\\\\Temp\\\\*.tmp").
        
    Returns:
        list[str]: List of expanded paths matching the glob pattern, or
                   [path] if no wildcards are present.
                   
    Example:
        >>> glob_like("C:\\\\Temp\\\\*.tmp")
        ['C:\\\\Temp\\\\file1.tmp', 'C:\\\\Temp\\\\file2.tmp']
        >>> glob_like("C:\\\\Windows\\\\Temp")
        ['C:\\\\Windows\\\\Temp']
    """
    if any(ch in path for ch in "*?["):
        return globmod.glob(path)
    return [path]


def _parallel_map(func: Callable, items, workers: int | None = None) -> list:
    """Apply a function to every item in parallel across multiple threads.
    
    Uses ThreadPoolExecutor to distribute work across up to `workers` threads
    (default: 4). Results are returned in the same order as the input items.
    Failed tasks yield None instead of raising exceptions.
    
    Args:
        func (Callable): Function to apply to each item. Should handle its
                        own exceptions or be exception-safe.
        items (Iterable): Collection of items to process.
        workers (int | None, optional): Maximum number of threads. Defaults to
                                        DEFAULT_WORKERS (4). Capped at len(items).
                                        
    Returns:
        list: Results in the same order as items. Failed tasks return None.
        
    Notes:
        - Single-item optimization: If len(items) == 1 or workers == 1, runs
          synchronously without ThreadPoolExecutor overhead.
        - Error handling: Exceptions in func are caught and None is returned
          for that item, preventing one failure from stopping the entire batch.
        - Thread count: Capped at min(len(items), workers) to avoid creating
          more threads than items.
        - Disk I/O: The default worker count (4) is tuned to avoid disk thrashing
          on mechanical drives while still providing parallelism for SSDs.
    """
    items = list(items)
    if not items:
        return []
    if len(items) == 1 or workers == 1:
        try:
            return [func(items[0])]
        except Exception:
            return [None]
    w = min(len(items), workers or DEFAULT_WORKERS)
    with ThreadPoolExecutor(max_workers=w) as pool:
        futures = [pool.submit(func, it) for it in items]
        out = []
        for f in futures:
            try:
                out.append(f.result())
            except Exception:
                out.append(None)
        return out


def _iter_tree_files(folder: str, should_cancel=None, recurse: bool = True):
    """Yield a DirEntry per regular file under `folder` (depth-first traversal).
    
    This is the core filesystem traversal function used by scanning, preview,
    and deletion operations. It uses os.scandir() for cached stat information,
    avoiding the old os.walk() + os.path.getsize() pattern that paid one extra
    syscall per file (a measured hotspot with 20k+ winapp targets).
    
    Args:
        folder (str): Absolute path to the root folder to traverse.
        should_cancel (callable, optional): Zero-argument function that returns
                                           True to stop traversal early.
        recurse (bool, optional): If True, traverse subdirectories recursively.
                                  If False, only traverse the top level. Defaults to True.
                                  
    Yields:
        os.DirEntry: Directory entry for each regular file (not directories).
        
    Notes:
        - Performance: Uses os.scandir() which provides cached is_dir/is_file
          and stat() information, avoiding redundant syscalls.
        - Junction safety: Never descends into junctions/reparse points.
          os.scandir reports them as directories, so without this check, a walk
          would traverse INTO the junction target and count/delete content that
          lives outside the physical tree (e.g., inside a protected user folder).
        - Error handling: OSError on any entry just skips that subtree/file.
        - Cooperative cancellation: Checks should_cancel() between entries.
        - Depth-first: Uses a stack-based approach for memory efficiency.
    """
    stack = []
    try:
        stack.append(os.scandir(folder))
    except OSError:
        return
    while stack:
        if should_cancel and should_cancel():
            return
        try:
            entry = next(stack[-1])
        except StopIteration:
            stack.pop().close()
            continue
        except OSError:
            stack.pop().close()
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                if os.path.isjunction(entry.path) or not recurse:
                    continue
                sub = os.scandir(entry.path)
                if sub is not None:
                    stack.append(sub)
            elif entry.is_file(follow_symlinks=False):
                yield entry
        except OSError:
            continue


def iter_file_sizes(folder: str, should_cancel=None) -> Generator[tuple[str, int], None, None]:
    """Generator walking a folder with os.scandir (cached stat) yielding (path, size_bytes).
    
    This is a convenience wrapper around _iter_tree_files that extracts the
    file size from each DirEntry's stat() information. Faster than os.walk()
    + getsize() (one syscall less per file).
    
    Args:
        folder (str): Absolute path to the root folder to traverse.
        should_cancel (callable, optional): Zero-argument function that returns
                                           True to stop traversal early.
                                           
    Yields:
        tuple[str, int]: (absolute_path, size_in_bytes) for each regular file.
        
    Notes:
        - Never descends into junctions (inherited from _iter_tree_files).
        - OSError on any entry just skips that subtree/file.
        - Used by _fast_folder_stats() for size counting.
    """
    for entry in _iter_tree_files(folder, should_cancel):
        try:
            yield entry.path, entry.stat().st_size
        except OSError:
            continue


def _fast_folder_stats(folder: str, on_progress=None, should_cancel=None) -> tuple[int, int]:
    """Walk a folder with os.scandir (cached stat), much faster than os.walk + getsize.
    
    This function calculates the total size and file count of a folder using
    the optimized iter_file_sizes() generator. It's the primary method for
    measuring folder sizes during scanning.
    
    Args:
        folder (str): Absolute path to the folder to measure.
        on_progress (callable, optional): Function called with file count every
                                          PROGRESS_STATS files (default: 500).
        should_cancel (callable, optional): Zero-argument function that returns
                                           True to stop traversal early.
                                           
    Returns:
        tuple[int, int]: (total_size_bytes, total_file_count)
        
    Notes:
        - Performance: Uses os.scandir() for cached stat information.
        - Progress reporting: Every PROGRESS_STATS files to avoid UI flooding.
        - Error handling: Silently ignores OSError on individual files.
    """
    total_size = 0
    total_files = 0
    for _path, size in iter_file_sizes(folder, should_cancel):
        total_size += size
        total_files += 1
        if on_progress and total_files % PROGRESS_STATS == 0:
            on_progress(total_files)
    return total_size, total_files


def _folder_size(folder: str) -> int:
    """Calculate the total size of a folder (scandir, cached stat).
    
    Convenience wrapper around _fast_folder_stats() that returns only the
    size component.
    
    Args:
        folder (str): Absolute path to the folder to measure.
        
    Returns:
        int: Total size in bytes of all files in the folder.
    """
    return _fast_folder_stats(folder)[0]


def _delete_path(path: str) -> bool:
    """Delete a file or a whole folder tree.
    
    Returns True when the path is gone afterwards (rmtree runs with
    ignore_errors, so the existence check is the source of truth).
    
    Guarded by the delete safety layer: protected roots (user profile,
    Windows dir, drive root, ...) and folder targets under protected user
    folders are refused.
    
    Args:
        path (str): Absolute path to the file or folder to delete.
        
    Returns:
        bool: True if the path was successfully deleted, False otherwise.
        
    Notes:
        - Safety check: Calls is_safe_delete_target() before any deletion.
        - Folders: Uses shutil.rmtree() with ignore_errors=True.
        - Symlinks/junctions: Removed without following their targets.
        - Read-only files: Made writable before deletion attempt.
    """
    if not is_safe_delete_target(
            path, is_dir=os.path.isdir(path) or os.path.isjunction(path)):
        return False
    try:
        if os.path.isdir(path):
            if os.path.islink(path) or os.path.isjunction(path):
                _remove_link(path)
            else:
                shutil.rmtree(path, ignore_errors=True)
            return not os.path.exists(path)
        os.remove(path)
        return not os.path.exists(path)
    except OSError:
        return False


def _make_writable(path: str) -> None:
    """Clear the read-only attribute (Windows) so the file can be removed.
    
    Windows files with the read-only attribute cannot be deleted directly.
    This function removes the read-only flag by setting the file permissions
    to read+write.
    
    Args:
        path (str): Absolute path to the file.
        
    Notes:
        - Silently ignores OSError if the chmod fails (file may already be writable).
        - Called before retrying deletion after an access-denied error.
    """
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _safe_rmdir(path: str, errors: list[DeleteError] | None = None) -> None:
    """Remove an empty directory, tolerating read-only attributes.
    
    Attempts to remove the directory. If it fails due to read-only attributes,
    makes the directory writable and retries. All errors are collected in the
    errors list if provided.
    
    Args:
        path (str): Absolute path to the directory to remove.
        errors (list[DeleteError] | None, optional): List to append DeleteError
                                                     objects to. If None, errors
                                                     are silently ignored.
                                                     
    Notes:
        - Only works on empty directories (use shutil.rmtree for non-empty).
        - Two-attempt strategy: First attempt may fail due to read-only flag.
        - Error collection: If errors list is provided, both attempts are logged.
    """
    try:
        os.rmdir(path)
    except OSError as e:
        if errors is not None:
            errors.append(_make_error(path, "rmdir", e))
        _make_writable(path)
        try:
            os.rmdir(path)
        except OSError as e2:
            if errors is not None:
                errors.append(_make_error(path, "rmdir", e2))


def _remove_link(path: str) -> None:
    """Remove a symlink or junction *link* without touching its target.
    
    shutil.rmtree silently leaves junctions in place on Windows
    (ignore_errors swallows the failure), so links are removed with
    os.rmdir/os.remove first; rmtree is only the last-resort fallback.
    
    Args:
        path (str): Absolute path to the symlink or junction to remove.
        
    Notes:
        - Junctions and directory symlinks: Removed with os.rmdir().
        - File symlinks: Removed with os.remove().
        - Fallback: If both fail, attempts shutil.rmtree() with ignore_errors.
        - Critical: Never follows the link to delete the target.
    """
    try:
        os.rmdir(path)   # junctions and directory symlinks
        return
    except OSError:
        pass
    try:
        os.remove(path)  # file symlinks
        return
    except OSError:
        pass
    shutil.rmtree(path, ignore_errors=True)


def _delete_measured(path: str) -> tuple[bool, int, list[DeleteError]]:
    """Delete a file or a whole folder tree in ONE traversal, returning
    (gone, freed_bytes, errors).
    
    This is the core deletion function. It measures the size and deletes
    the target in a single pass, avoiding the old measure-then-rmtree
    pattern that scanned twice (doubling I/O on multi-GB temp/cache trees).
    
    Args:
        path (str): Absolute path to the file or folder to delete.
        
    Returns:
        tuple[bool, int, list[DeleteError]]: 
            - gone (bool): True if the path no longer exists after deletion.
            - freed_bytes (int): Total bytes freed by the deletion.
            - errors (list[DeleteError]): List of detailed error objects for
                                          any failures during deletion.
                                          
    Notes:
        - Single-pass optimization: Measures size from DirEntry stats while
          deleting, avoiding a separate measurement pass.
        - Forgiving semantics: Follows shutil.rmtree(ignore_errors=True)
          semantics: read-only files become writable, failures leave leftovers,
          and symlinks/junctions are removed without following their target.
        - Error collection: Every failure is kept in `errors` (path, operation,
          kind, code, message) instead of being swallowed, so the UI can
          report _what_ failed and why (P0-5).
        - Safety gate: A guarded target (protected root, drive root, or a
          folder under a protected user folder) is refused here, before any
          filesystem access (P0-2). The gate receives the caller's intent
          (is_dir) so a whole folder under Documents is refused while
          individual files there stay cleanable.
        - Junction handling: Symlinks/junctions are removed with _remove_link()
          without following their targets.
        - Read-only handling: Files are made writable with _make_writable()
          before retrying deletion after an access-denied error.
    """
    is_dir = os.path.isdir(path) or os.path.isjunction(path)
    if not is_safe_delete_target(path, is_dir=is_dir):
        return False, 0, [_make_error(path, "safety", None,
                                      kind="safety",
                                      message="refused by delete safety policy")]
    if not is_dir or os.path.islink(path) or os.path.isjunction(path):
        # Regular file or a top-level symlink/junction (never followed).
        size = 0
        errors: list[DeleteError] = []
        try:
            size = os.path.getsize(path)
        except OSError as e:
            errors.append(_make_error(path, "stat", e))
        try:
            if os.path.isdir(path):
                if os.path.islink(path) or os.path.isjunction(path):
                    _remove_link(path)
                else:
                    shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except OSError as e:
            errors.append(_make_error(path, "remove", e))
            _make_writable(path)
            try:
                if os.path.isdir(path):
                    if os.path.islink(path) or os.path.isjunction(path):
                        _remove_link(path)
                    else:
                        shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
            except OSError as e2:
                errors.append(_make_error(path, "remove", e2))
        if not os.path.exists(path):
            return True, size, []
        return False, size, errors or [DeleteError(
            path=path, operation="remove", kind="other",
            message="path still exists after deletion")]

    freed = 0
    errors = []
    stack = []
    try:
        stack.append((path, os.scandir(path)))
    except OSError as e:
        errors.append(_make_error(path, "scandir", e))
        return not os.path.exists(path), freed, errors

    def _remove_file(entry, op="remove") -> None:
        nonlocal freed
        if not os.path.lexists(entry.path):
            return
        try:
            freed += entry.stat().st_size
        except FileNotFoundError:
            return
        except OSError as e:
            errors.append(_make_error(entry.path, "stat", e))
        try:
            os.remove(entry.path)
        except FileNotFoundError:
            return
        except OSError as e:
            errors.append(_make_error(entry.path, op, e))
            _make_writable(entry.path)
            try:
                os.remove(entry.path)
            except OSError as e2:
                errors.append(_make_error(entry.path, op, e2))

    while stack:
        try:
            entry = next(stack[-1][1])
        except StopIteration:
            d, it = stack.pop()
            it.close()
            _safe_rmdir(d, errors)
            continue
        except OSError as e:
            d, it = stack.pop()
            it.close()
            errors.append(_make_error(d, "scandir", e))
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                if os.path.islink(entry.path) or os.path.isjunction(entry.path):
                    # Junction/symlink: remove the link, never its target.
                    try:
                        _remove_link(entry.path)
                    except OSError as e:
                        errors.append(_make_error(entry.path, "rmtree", e))
                    continue
                sub = os.scandir(entry.path)
                if sub is not None:
                    stack.append((entry.path, sub))
            else:
                _remove_file(entry)
        except OSError as e:
            errors.append(_make_error(entry.path, "remove", e))
            continue
    _safe_rmdir(path, errors)
    return not os.path.exists(path), freed, errors


def _safe_size(path: str) -> int:
    """Size of a file or folder, 0 on any error (never raises).
    
    Convenience function that safely calculates the size of a path,
    returning 0 if any error occurs (e.g., path doesn't exist, permission denied).
    
    Args:
        path (str): Absolute path to the file or folder.
        
    Returns:
        int: Size in bytes, or 0 if the path doesn't exist or can't be read.
    """
    try:
        if os.path.isdir(path):
            return _folder_size(path)
        return os.path.getsize(path)
    except OSError:
        return 0


def _errlog(msg: str, level: str = "error", component: str = "") -> None:
    """Append a JSONL record to the error log (the app has no console:
    failures must leave a trace). Developer-facing, English.
    
    Each line is a structured record: {"ts", "level", "component", "msg"}
    so failures can be queried by severity or source module. `level` is
    "error" by default for backwards compatibility with callers that only
    pass a message; `component` defaults to the calling module name.
    
    Args:
        msg (str): The error message to log.
        level (str, optional): Log level ("error", "warning", "info"). Defaults to "error".
        component (str, optional): Source component (module name). Defaults to
                                   the caller's module name (auto-detected).
                                   
    Notes:
        - Log location: %LOCALAPPDATA%/LimpiaPro/logs/limpiapro_error.log
        - Format: JSON Lines (one JSON object per line) for easy parsing.
        - Error resilience: If logging itself fails, the error is silently
          ignored to prevent cascading failures.
        - Component detection: Uses sys._getframe(1) to auto-detect the caller's
          module name if not provided.
    """
    if not component:
        try:
            component = sys._getframe(1).f_globals.get("__name__", "?")
        except Exception:
            component = "?"
    record = json.dumps({
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "component": component,
        "msg": str(msg),
    }, ensure_ascii=False)
    try:
        with open(os.path.join(get_logs_dir(), "limpiapro_error.log"),
                  "a", encoding="utf-8") as f:
            f.write(record + "\n")
    except Exception:
        pass  # nosec B110 - error logging must never itself fail


def _oem_cp() -> str:
    """Get the OEM code page (cp850...) for Windows console tools.
    
    Windows console tools (schtasks, tasklist, etc.) emit output in the OEM
    code page, not UTF-8. This function retrieves the current OEM code page
    to properly decode their output and fix mojibake of accented characters.
    
    Returns:
        str: The OEM code page as a string (e.g., "850", "437"). Defaults to "850".
        
    Notes:
        - Used by run_system_cmd() to decode stdout/stderr correctly.
        - Defaults to cp850 (Western European) if the API call fails.
    """
    try:
        cp = ctypes.windll.kernel32.GetOEMCP()
        return str(int(cp) or 850)
    except Exception:
        return "850"


def run_system_cmd(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a Windows console command without a window, capturing stdout/stderr.
    
    Executes a command with proper encoding handling for Windows console tools.
    The output is decoded using the OEM code page to fix mojibake of accented
    characters in tasks and processes (those tools write to the pipe in the
    OEM code page, not UTF-8).
    
    Args:
        args (list[str]): Command and arguments as a list (no shell=True for security).
        timeout (int, optional): Maximum execution time in seconds. Defaults to 60.
        
    Returns:
        subprocess.CompletedProcess: Object with .returncode, .stdout, .stderr.
        
    Notes:
        - Security: Uses args list instead of shell=True to prevent command injection.
        - Encoding: Decodes stdout/stderr with the OEM code page (cp850, etc.).
        - Window: Uses CREATE_NO_WINDOW flag to hide the console window.
        - Error handling: errors="replace" for invalid characters in output.
        - Timeout: Raises subprocess.TimeoutExpired if the command exceeds timeout.
        
    Example:
        >>> result = run_system_cmd(["tasklist", "/FI", "IMAGENAME eq python.exe"])
        >>> print(result.stdout)
    """
    return subprocess.run(  # nosec B603 - caller supplies arg list, no shell
        args, capture_output=True, text=True,
        encoding=f"cp{_oem_cp()}", errors="replace",
        timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
