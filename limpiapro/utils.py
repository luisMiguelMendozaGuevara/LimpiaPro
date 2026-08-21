"""Common utilities: paths, formatting, deletion and folder measuring."""

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

# Progress: how many files between scan notifications.
PROGRESS_STATS = 500
PROGRESS_RULES = 100
PROGRESS_DELETE = 20
DEFAULT_WORKERS = 4


# Windows error codes (winerror) used to classify deletion failures.
_WINERROR_IN_USE = 32          # ERROR_SHARING_VIOLATION
_WINERROR_ACCESS_DENIED = 5    # ERROR_ACCESS_DENIED
_WINERROR_NOT_FOUND = 2        # ERROR_FILE_NOT_FOUND
_WINERROR_PATH_NOT_FOUND = 3   # ERROR_PATH_NOT_FOUND
_WINERROR_DIR_NOT_EMPTY = 145  # ERROR_DIR_NOT_EMPTY


@dataclass
class DeleteError:
    """One failed deletion with enough detail to diagnose it.

    Used by _delete_measured/_delete_path so the UI can report exactly
    which path failed, why and with what kind of failure instead of a bare
    "n errors" counter."""
    path: str
    operation: str              # "remove" | "rmtree" | "rmdir" | "safety"
    kind: str                   # see _classify_error kind values
    code: int = 0               # winerror when available, else errno
    message: str = ""


def _winerror(e: OSError) -> int:
    """Preferred error code for diagnostics: winerror, then errno."""
    return int(getattr(e, "winerror", 0) or e.errno or 0)


def _classify_error(e: OSError) -> str:
    """Stable short kind for a deletion OSError:
    'in_use' | 'access_denied' | 'not_found' | 'readonly' | 'dir_not_empty'
    | 'other'."""
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
    policy rejection where there is no underlying exception)."""
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
    """True when `path` is exactly a drive root like 'C:\\'."""
    return SafetyGuard.is_drive_root(path)


def app_dir() -> str:
    """Application directory (works packaged with PyInstaller too).

    In development it is the project root: the folder holding
    limpiador.py, winapp2.ini, the cache file and the error log."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_admin() -> bool:
    """True when the process runs elevated (UAC administrator)."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def format_size(num: float) -> str:
    """Human-readable size (bytes -> KB/MB/...); '-' for negatives."""
    if isinstance(num, int) and num < 0:
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024.0:
            return f"{num:.1f} {unit}" if unit != "B" else f"{int(num)} B"
        num /= 1024.0
    return f"{num:.1f} PB"


def glob_like(path: str) -> list[str]:
    """glob.glob() when the path carries wildcards (*?[), else [path]
    (no filesystem access for plain paths)."""
    if any(ch in path for ch in "*?["):
        return globmod.glob(path)
    return [path]


def _parallel_map(func: Callable, items, workers: int | None = None) -> list:
    """Apply func to every item across up to `workers` threads (4 by
    default). Results come back in order; a failed task yields None.
    The thread count is capped to keep the disk from thrashing."""
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


def iter_file_sizes(folder: str, should_cancel=None) -> Generator[tuple[str, int], None, None]:
    """Generator walking a folder with os.scandir (cached stat) yielding
    (path, size_bytes) per regular file. Faster than os.walk + getsize
    (one syscall less per file).

    Iterative (an explicit stack of scandir iterators) instead of
    recursive to survive deep trees without hitting the recursion limit;
    OSError on any entry just skips that subtree/file. When
    `should_cancel` (a callable) turns truthy the walk stops early.

    Junctions/reparse points are never descended into (os.scandir reports
    them as directories, so without this check a scan would walk INTO a
    junction target and count — or later delete — content that lives
    outside the physical tree, e.g. inside a protected user folder)."""
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
            if entry.is_dir(follow_symlinks=False) and not os.path.isjunction(entry.path):
                sub = os.scandir(entry.path)
                if sub is not None:
                    stack.append(sub)
            elif entry.is_file(follow_symlinks=False):
                yield entry.path, entry.stat().st_size
        except OSError:
            continue


def _fast_folder_stats(folder: str, on_progress=None, should_cancel=None) -> tuple[int, int]:
    """Walk a folder with os.scandir (cached stat), much faster than
    os.walk + getsize. Returns (size_bytes, file_count)."""
    total_size = 0
    total_files = 0
    for _path, size in iter_file_sizes(folder, should_cancel):
        total_size += size
        total_files += 1
        if on_progress and total_files % PROGRESS_STATS == 0:
            on_progress(total_files)
    return total_size, total_files


def _folder_size(folder: str) -> int:
    """Total size of a folder (scandir, cached stat)."""
    return _fast_folder_stats(folder)[0]


def _delete_path(path: str) -> bool:
    """Delete a file or a whole folder tree. Returns True when the path is
    gone afterwards (rmtree runs with ignore_errors, so the existence
    check is the source of truth).

    Guarded by the delete safety layer: protected roots (user profile,
    Windows dir, drive root, ...) and folder targets under protected user
    folders are refused."""
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
    """Clear the read-only attribute (Windows) so the file can be removed."""
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _safe_rmdir(path: str, errors: list[DeleteError] | None = None) -> None:
    """Remove an empty directory, tolerating read-only attributes."""
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
    os.rmdir/os.remove first; rmtree is only the last-resort fallback."""
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

    Folder sizes are tallied straight from the cached os.scandir entry
    stats while the tree is being removed, so a directory is walked only
    once (the old measure-then-rmtree pattern scanned it twice, which
    doubled the I/O on multi-GB temp/cache trees).

    Follows the forgiving semantics of rmtree(ignore_errors=True):
    read-only files become writable, failures leave leftovers, and
    symlinks/junctions are removed without following their target. Every
    failure is kept in `errors` (path, operation, kind, code, message)
    instead of being swallowed, so the UI can report _what_ failed and
    why (P0-5).

    A guarded target (protected root, drive root, or a folder under a
    protected user folder) is refused here, before any filesystem access
    (P0-2). The gate receives the caller's intent (is_dir) so a whole
    folder under Documents is refused while individual files there stay
    cleanable."""
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
    """Size of a file or folder, 0 on any error (never raises)."""
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
    pass a message; `component` defaults to the calling module name."""
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
    """OEM code page (cp850...): Windows console tools (schtasks,
    tasklist) emit there, not in UTF-8."""
    try:
        cp = ctypes.windll.kernel32.GetOEMCP()
        return str(int(cp) or 850)
    except Exception:
        return "850"


def run_system_cmd(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a Windows console command without a window, capturing
    stdout/stderr decoded with the OEM code page.

    Returns the subprocess.CompletedProcess (.returncode, .stdout,
    .stderr). Fixes the mojibake of accented characters in tasks and
    processes (those tools write to the pipe in the OEM code page)."""
    return subprocess.run(  # nosec B603 - caller supplies arg list, no shell
        args, capture_output=True, text=True,
        encoding=f"cp{_oem_cp()}", errors="replace",
        timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
