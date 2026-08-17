"""Common utilities: paths, formatting, deletion and folder measuring."""

import ctypes
import glob as globmod
import os
import shutil
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Generator, List, Optional, Tuple

# Progress: how many files between scan notifications.
PROGRESS_STATS = 500
PROGRESS_RULES = 100
PROGRESS_DELETE = 20
DEFAULT_WORKERS = 4


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


def glob_like(path: str) -> List[str]:
    """glob.glob() when the path carries wildcards (*?[), else [path]
    (no filesystem access for plain paths)."""
    if any(ch in path for ch in "*?["):
        return globmod.glob(path)
    return [path]


def _parallel_map(func: Callable, items, workers: Optional[int] = None) -> list:
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


def iter_file_sizes(folder: str) -> Generator[Tuple[str, int], None, None]:
    """Generator walking a folder with os.scandir (cached stat) yielding
    (path, size_bytes) per regular file. Faster than os.walk + getsize
    (one syscall less per file).

    Iterative (an explicit stack of scandir iterators) instead of
    recursive to survive deep trees without hitting the recursion limit;
    OSError on any entry just skips that subtree/file."""
    stack = []
    try:
        stack.append(os.scandir(folder))
    except OSError:
        return
    while stack:
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
                sub = os.scandir(entry.path)
                if sub is not None:
                    stack.append(sub)
            elif entry.is_file(follow_symlinks=False):
                yield entry.path, entry.stat().st_size
        except OSError:
            continue


def _fast_folder_stats(folder: str, on_progress=None) -> Tuple[int, int]:
    """Walk a folder with os.scandir (cached stat), much faster than
    os.walk + getsize. Returns (size_bytes, file_count)."""
    total_size = 0
    total_files = 0
    for _path, size in iter_file_sizes(folder):
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
    check is the source of truth)."""
    try:
        if os.path.isdir(path):
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


def _safe_rmdir(path: str) -> None:
    """Remove an empty directory, tolerating read-only attributes."""
    try:
        os.rmdir(path)
    except OSError:
        _make_writable(path)
        try:
            os.rmdir(path)
        except OSError:
            pass


def _delete_measured(path: str) -> Tuple[bool, int]:
    """Delete a file or a whole folder tree in ONE traversal, returning
    (gone, freed_bytes).

    Folder sizes are tallied straight from the cached os.scandir entry
    stats while the tree is being removed, so a directory is walked only
    once (the old measure-then-rmtree pattern scanned it twice, which
    doubled the I/O on multi-GB temp/cache trees).

    Follows the forgiving semantics of rmtree(ignore_errors=True):
    read-only files become writable, failures leave leftovers, and
    symlinks/junctions are removed without following their target."""
    if not os.path.isdir(path) or os.path.islink(path) or os.path.isjunction(path):
        # Regular file or a top-level symlink/junction (never followed).
        size = 0
        try:
            size = os.path.getsize(path)
        except OSError:
            pass
        try:
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
            else:
                os.remove(path)
        except OSError:
            _make_writable(path)
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    os.remove(path)
            except OSError:
                pass
        return not os.path.exists(path), size

    freed = 0
    stack = []
    try:
        stack.append((path, os.scandir(path)))
    except OSError:
        return not os.path.exists(path), freed

    def _remove_file(entry) -> None:
        nonlocal freed
        try:
            freed += entry.stat().st_size
        except OSError:
            pass
        try:
            os.remove(entry.path)
        except OSError:
            _make_writable(entry.path)
            try:
                os.remove(entry.path)
            except OSError:
                pass

    while stack:
        try:
            entry = next(stack[-1][1])
        except StopIteration:
            d, it = stack.pop()
            it.close()
            _safe_rmdir(d)
            continue
        except OSError:
            d, it = stack.pop()
            it.close()
            continue
        try:
            if entry.is_dir(follow_symlinks=False):
                if os.path.islink(entry.path) or os.path.isjunction(entry.path):
                    # Junction/symlink: remove the link, never its target.
                    try:
                        shutil.rmtree(entry.path, ignore_errors=True)
                    except OSError:
                        pass
                    continue
                sub = os.scandir(entry.path)
                if sub is not None:
                    stack.append((entry.path, sub))
            else:
                _remove_file(entry)
        except OSError:
            continue
    _safe_rmdir(path)
    return not os.path.exists(path), freed


def _safe_size(path: str) -> int:
    """Size of a file or folder, 0 on any error (never raises)."""
    try:
        if os.path.isdir(path):
            return _folder_size(path)
        return os.path.getsize(path)
    except OSError:
        return 0


def _errlog(msg: str) -> None:
    """Append to the error log file (the app has no console: failures must
    leave a trace). Developer-facing, English."""
    try:
        with open(os.path.join(app_dir(), "limpiapro_error.log"),
                  "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def _oem_cp() -> str:
    """OEM code page (cp850...): Windows console tools (schtasks,
    tasklist) emit there, not in UTF-8."""
    try:
        cp = ctypes.windll.kernel32.GetOEMCP()
        return str(int(cp) or 850)
    except Exception:
        return "850"


def run_system_cmd(args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Run a Windows console command without a window, capturing
    stdout/stderr decoded with the OEM code page.

    Returns the subprocess.CompletedProcess (.returncode, .stdout,
    .stderr). Fixes the mojibake of accented characters in tasks and
    processes (those tools write to the pipe in the OEM code page)."""
    return subprocess.run(
        args, capture_output=True, text=True,
        encoding=f"cp{_oem_cp()}", errors="replace",
        timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
