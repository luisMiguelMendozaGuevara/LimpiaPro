"""Central delete-safety policy (SafetyGuard).

Every destructive operation in LimpiaPro passes through this gate
immediately before touching the filesystem. This module is the absolute
authority on what can and cannot be deleted.

Policy Overview:
    * **Exact refusal** — drive roots, system directories (C:\\Windows,
      Program Files, ...), environment roots (USERPROFILE, APPDATA, ...)
      and the well-known user folders (Desktop, Documents, Downloads,
      Music, Pictures, Videos, ...) can never be deletion targets.

    * **Descendant refusal (folder targets only)** — a *folder* that lives
      under a protected user folder can never be removed recursively
      (the reported "Documents" incident is exactly this class of bug:
      a descendant folder passed the old exact-match gate and was
      rmtree'd whole). Individual *files* anywhere stay cleanable: that
      is the cleanup itself, and winapp2 legitimately removes files under
      e.g. %UserProfile%\\Documents\\App\\logs.

    * **Reparse points / junctions** — the real final path (os.path.realpath,
      which resolves junctions on Windows) is checked, so a target
      reached *through* a junction that resolves into a protected area
      is refused even when the literal path looks harmless. Walks in
      categories.py / utils.iter_file_sizes never descend into junctions.

    * **Critical-file deny-list (Lote D5)** — winapp2.ini is user-loadable,
      so its rules are untrusted input for this gate. OS-critical files
      (kernel32.dll, explorer.exe, boot components, page files, registry
      hives, ...) are refused BY BASENAME everywhere, and the OS binary
      trees (System32, SysWOW64, Boot) refuse every descendant target:
      no hostile or buggy rule can prune inside the operating system.
      Explicitly cleanable sub-trees (LogFiles, spool PRINTERS,
      winevt Logs) stay whitelisted for *file* targets only.

Architecture Notes:
    - The old flat helper `is_safe_delete_target(path)` in utils.py remains as
      a thin wrapper (tests and categories import it from there); the policy
      lives here so the UI can never bypass it.
    - Root sets are computed lazily and cached for performance. Call invalidate()
      when the environment may have changed (tests, user profile relocation).
    - Parent chain memoization: Thousands of file targets share the same parents,
      so the junction-check is cached per parent directory (capped at 4096 entries).

Security Guarantees:
    - The UI can request a clean, but it NEVER decides which paths are safe.
    - All deletion operations (utils._delete_measured, categories.clean) call
      is_safe_delete_target() immediately before filesystem access.
    - Junction traversal attacks are prevented by resolving realpath and checking
      the resolved path against protected roots.
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import re
from collections import OrderedDict
from ctypes import wintypes

# Well-known user folders (FOLDERID constants). Their real locations are
# resolved through SHGetKnownFolderPath because they can be redirected
# (e.g. Documents on D:\\ or under OneDrive) — a guard on
# %USERPROFILE%\\Documents alone would miss the real folder.
_FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
_FOLDERID_DOCUMENTS = "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}"
_FOLDERID_DOWNLOADS = "{374DE290-123F-4565-9164-39C4925E467B}"
_FOLDERID_MUSIC = "{4BD8D571-6D19-48D3-BE97-422220080E43}"
_FOLDERID_PICTURES = "{33E28130-4E1E-4676-835A-98395C3BC3BB}"
_FOLDERID_VIDEOS = "{18989B1D-99B5-455B-841C-AB7C74E4DDFC}"
_FOLDERID_FAVORITES = "{1777F761-68AD-4D8A-87BD-30B759FA33DD}"
_FOLDERID_LINKS = "{BFB9D5E0-C6A9-404C-B2B2-AE6DB6AF4968}"
_FOLDERID_CONTACTS = "{56784854-C6CB-462B-8169-88E350ACB882}"
_FOLDERID_SAVED_GAMES = "{4C5C32FF-BB9D-43B0-B5B4-2D72E54EAAA4}"
_FOLDERID_SEARCHES = "{7D1D3A04-DEBB-4115-95CF-2F29DA2920DA}"
_FOLDERID_ONEDRIVE = "{A52BBA46-e9E1-435F-B3D9-28DAA648C0F6}"

_KNOWN_USER_FOLDERS = (
    ("Desktop", _FOLDERID_DESKTOP),
    ("Documents", _FOLDERID_DOCUMENTS),
    ("Downloads", _FOLDERID_DOWNLOADS),
    ("Music", _FOLDERID_MUSIC),
    ("Pictures", _FOLDERID_PICTURES),
    ("Videos", _FOLDERID_VIDEOS),
    ("Favorites", _FOLDERID_FAVORITES),
    ("Links", _FOLDERID_LINKS),
    ("Contacts", _FOLDERID_CONTACTS),
    ("Saved Games", _FOLDERID_SAVED_GAMES),
    ("Searches", _FOLDERID_SEARCHES),
    ("OneDrive", _FOLDERID_ONEDRIVE),
)

# System directories that must never be removed as a whole. Unlike the
# user folders above, only the *exact* path is protected: cleaning
# C:\\Windows\\Temp or C:\\Windows\\Prefetch is legitimate, so their
# descendants must stay removable.
_SYSTEM_GUARD_DIRS = {
    r"C:\Windows",
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData",
    r"C:\Users",
    r"C:\Users\Default",
    r"C:\Users\Public",
}

_ENV_ROOTS = ("USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
              "PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramData")

# KF_FLAG_DONT_VERIFY: return the configured path without requiring it to
# exist (redirected-but-missing folders must still be protected).
_KF_FLAG_DONT_VERIFY = 0x00004000

# Cap for the parent-chain memo used by the per-file fast path.
# Prevents unbounded memory growth in long-running sessions while still
# providing cache hits for the thousands of files sharing the same parent.
# Eviction is LRU (E3.1): the bundled winapp2.ini carries ~14k FileKeys,
# so one large clean touches far more than 4096 distinct parents — the
# old clear()-on-cap policy reset the hit-rate to zero mid-run and forced
# thousands of extra realpath syscalls.
_PARENT_CACHE_CAP = 4096

# --- Lote D5: critical-file deny-list ---------------------------------
# A winapp2.ini is user-loadable, so its rules are untrusted input for
# the deletion policy. These basenames are refused EVERYWHERE: no
# legitimate cleaning scenario deletes them, and a copy of e.g.
# kernel32.dll sitting in %TEMP% is suspicious rather than cleanable.
_CRITICAL_FILE_NAMES = frozenset({
    # Core NT / Win32 libraries
    "ntdll.dll", "kernel32.dll", "kernelbase.dll", "user32.dll",
    "gdi32.dll", "gdi32full.dll", "shell32.dll", "advapi32.dll",
    "ole32.dll", "oleaut32.dll", "rpcrt4.dll", "ucrtbase.dll",
    "msvcrt.dll", "combase.dll", "comctl32.dll", "shlwapi.dll",
    "sechost.dll", "win32u.dll", "ws2_32.dll", "wininet.dll",
    "winhttp.dll", "crypt32.dll", "msi.dll", "version.dll",
    # Kernel / boot components
    "ntoskrnl.exe", "ntkrnlpa.exe", "hal.dll", "win32k.sys",
    "ci.dll", "bootmgr", "bootmgr.efi", "bootmgfw.efi",
    "winload.exe", "winload.efi", "winresume.exe", "winresume.efi",
    # Core system processes
    "smss.exe", "csrss.exe", "wininit.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "svchost.exe", "explorer.exe",
    "dwm.exe", "conhost.exe", "cmd.exe", "powershell.exe",
    "regedit.exe", "taskmgr.exe",
    # Memory / page files and per-user registry hives
    "pagefile.sys", "swapfile.sys", "hiberfil.sys",
    "ntuser.dat", "usrclass.dat",
})

# OS binary trees: every descendant target (file OR folder) is refused —
# a rule must never prune inside the operating system itself. The system
# root is also resolved from %SystemRoot%/%WINDIR% so non-C: installs of
# Windows are covered too.
_CRITICAL_TREE_DIRS = (
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Windows\Boot",
)

# Explicitly cleanable sub-trees INSIDE a critical tree (relative prefix,
# backslash-separated, lowercased). Only *file* targets are exempt; the
# folders themselves are never removable.
_TREE_FILE_EXEMPT_PREFIXES = (
    "logfiles\\",          # IIS/HTTP and component log files
    "spool\\printers\\",    # printer spool jobs
    "winevt\\logs\\",      # event log files
)


def _canon(path: str) -> str:
    """Windows-style canonical form for deny-list comparisons.

    Backslash separators + lowercased: robust against separator style and
    letter case on every host OS (os.path.normcase is a no-op on POSIX,
    so the deny-list would otherwise miss case variants there).
    String-only: no syscalls, safe to call per deletion target.

    Args:
        path (str): Path to canonicalize (may contain %ENV% variables).

    Returns:
        str: Canonical lowercased backslash-separated form of `path`.
    """
    return os.path.normcase(os.path.normpath(
        os.path.expandvars(path))).lower().replace("/", "\\")


class _GUID(ctypes.Structure):
    """Windows GUID structure for SHGetKnownFolderPath API calls.
    
    This structure represents a globally unique identifier (GUID) used by
    Windows to identify known folders (FOLDERID constants). It's required
    for the SHGetKnownFolderPath API which resolves folder redirection
    (e.g., Documents moved to D:\\ or under OneDrive).
    """
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _parse_guid(text: str) -> _GUID:
    """Parse a GUID string into a _GUID structure.
    
    Converts a GUID string in the format "{XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX}"
    or "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX" into a _GUID structure suitable
    for passing to Windows APIs.
    
    Args:
        text (str): GUID string to parse.
        
    Returns:
        _GUID: Parsed GUID structure.
        
    Raises:
        ValueError: If the GUID string is malformed.
        
    Example:
        >>> guid = _parse_guid("{FDD39AD0-238F-46AF-ADB4-6C85480369C7}")
    """
    m = re.fullmatch(
        r"\{?([0-9a-fA-F]{8})-([0-9a-fA-F]{4})-([0-9a-fA-F]{4})"
        r"-([0-9a-fA-F]{4})-([0-9a-fA-F]{12})\}?",
        text.strip())
    if m is None:
        raise ValueError(f"invalid FOLDERID: {text!r}")
    g = _GUID()
    g.Data1 = int(m.group(1), 16)
    g.Data2 = int(m.group(2), 16)
    g.Data3 = int(m.group(3), 16)
    raw = bytes.fromhex(m.group(4) + m.group(5))
    for i in range(8):
        g.Data4[i] = raw[i]
    return g


def _known_folder_path(folder_id: str) -> str | None:
    """Get the real location of a Windows known folder (redirection-aware).
    
    Uses the SHGetKnownFolderPath API to resolve the actual path of a known
    folder, accounting for redirection (e.g., Documents moved to D:\\ or
    under OneDrive). This is critical because a guard on %USERPROFILE%\\Documents
    alone would miss the real folder if it's redirected.
    
    Args:
        folder_id (str): FOLDERID GUID string (e.g., "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}").
        
    Returns:
        str | None: Absolute path to the folder, or None if the API is unavailable
                    (non-Windows, restricted environment, API failure).
                    
    Notes:
        - Uses KF_FLAG_DONT_VERIFY to return the configured path even if the
          folder doesn't exist yet (redirected-but-missing folders must still
          be protected).
        - Frees the COM memory allocated by SHGetKnownFolderPath.
        - Silently returns None on any error (non-Windows platforms, API failures).
    """
    try:
        shell32 = ctypes.windll.shell32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.POINTER(_GUID), wintypes.DWORD, wintypes.HANDLE,
            ctypes.POINTER(ctypes.c_wchar_p)]
        shell32.SHGetKnownFolderPath.restype = ctypes.c_long
        out = ctypes.c_wchar_p()
        hr = shell32.SHGetKnownFolderPath(
            ctypes.byref(_parse_guid(folder_id)),
            _KF_FLAG_DONT_VERIFY, None, ctypes.byref(out))
        path = out.value
        if path:
            with contextlib.suppress(Exception):
                ctypes.windll.ole32.CoTaskMemFree(out)
        if hr == 0 and path:
            return path
    except Exception:  # nosec B110 - best-effort API probe; None falls back
        pass          # to %USERPROFILE%\\<Name> roots which stay protected
    return None


class SafetyGuard:
    """Central delete-safety policy (see module docstring).
    
    This is the singleton authority that determines whether a path is safe
    to delete. It maintains cached sets of protected roots (system directories,
    environment roots, known user folders) and provides the is_safe_delete_target()
    gate that all deletion operations must pass through.
    
    Root sets are computed lazily on first access and cached for performance.
    Call invalidate() when the environment may have changed (e.g., in tests,
    or if the user profile is relocated).
    
    Attributes:
        _exact_roots (frozenset[str] | None): Cached system dirs + environment roots.
        _user_roots (frozenset[str] | None): Cached well-known user folders.
        _parent_clean (dict[str, bool]): Memoized parent chain junction checks.
    """

    def __init__(self) -> None:
        """Initialize the SafetyGuard with empty caches.
        
        Root sets and parent chain memoization are computed lazily on first
        access to avoid startup overhead.
        """
        self._exact_roots: frozenset[str] | None = None
        self._user_roots: frozenset[str] | None = None
        # parent dir (normcased) -> True when its chain has no junction.
        # OrderedDict for O(1) LRU eviction at the cap (E3.1).
        self._parent_clean: OrderedDict[str, bool] = OrderedDict()
        # Lote D5: canonical critical trees + windows dir (lazy).
        self._critical_trees: frozenset[str] | None = None
        self._windows_dir: str | None = None

    # ------------------------------------------------------------- roots

    def invalidate(self) -> None:
        """Drop cached root sets (env / known folders may have changed).
        
        Call this when the environment may have changed (e.g., in tests, or if
        the user profile is relocated). The next access will recompute the
        root sets from the current environment.
        """
        self._exact_roots = None
        self._user_roots = None
        self._parent_clean.clear()
        self._critical_trees = None
        self._windows_dir = None

    def exact_roots(self) -> frozenset[str]:
        """Get system dirs + environment roots: refused as exact targets.
        
        These paths are protected as exact matches only. Their descendants
        (e.g., C:\\Windows\\Temp) are allowed because cleaning them is
        legitimate.
        
        Returns:
            frozenset[str]: Normalized, absolute paths of system directories
                           and environment roots (USERPROFILE, APPDATA, etc.).
        """
        if self._exact_roots is None:
            roots = {os.path.normcase(os.path.normpath(d))
                     for d in _SYSTEM_GUARD_DIRS}
            for var in _ENV_ROOTS:
                value = os.environ.get(var)
                if value:
                    roots.add(os.path.normcase(os.path.normpath(value)))
            self._exact_roots = frozenset(roots)
        return self._exact_roots

    def protected_user_roots(self) -> frozenset[str]:
        """Get well-known user folders (real locations + %USERPROFILE% fallbacks).
        
        These paths are protected as exact targets AND as ancestors of folder
        targets. A *folder* under Documents cannot be deleted recursively,
        but individual *files* under Documents can be deleted (that's the
        cleanup itself).
        
        Returns:
            frozenset[str]: Normalized, absolute paths of well-known user folders
                           (Desktop, Documents, Downloads, etc.), resolved via
                           SHGetKnownFolderPath to account for redirection.
        """
        if self._user_roots is None:
            roots: set[str] = set()
            profile = os.environ.get("USERPROFILE")
            for name, folder_id in _KNOWN_USER_FOLDERS:
                real = _known_folder_path(folder_id)
                if real:
                    roots.add(os.path.normcase(os.path.normpath(real)))
                if profile:
                    roots.add(os.path.normcase(
                        os.path.normpath(os.path.join(profile, name))))
            self._user_roots = frozenset(roots)
        return self._user_roots

    # ------------------------------------------------- critical deny-list

    def _critical_tree_roots(self) -> frozenset[str]:
        """Get canonical OS binary trees (hardcoded + SystemRoot-derived).

        Also resolves the Windows directory (cached in ``self._windows_dir``)
        from %SystemRoot%/%WINDIR% when available, so non-C: installs stay
        protected. Computed lazily once and cached until invalidate().

        Returns:
            frozenset[str]: Canonical (backslash, lowercased) tree prefixes.
        """
        if self._critical_trees is None:
            trees = {_canon(d) for d in _CRITICAL_TREE_DIRS}
            # Windows env var names keep their documented casing (ruff's
            # SIM112 upper-casing would break Linux/test lookups where the
            # exact name matters).
            sysroot = (os.environ.get("SystemRoot")  # noqa: SIM112 - Windows name
                       or os.environ.get("WINDIR"))
            if sysroot:
                base = _canon(sysroot)
                self._windows_dir = base
                trees.update(base + "\\" + leaf for leaf in
                             ("system32", "syswow64", "boot"))
            else:
                self._windows_dir = _canon(r"C:\Windows")
            self._critical_trees = frozenset(trees)
        return self._critical_trees

    @staticmethod
    def _deny_parts(norm: str) -> tuple[str, str]:
        """Split a normalized path into (parent, basename) canonically.

        Both separators are unified to backslash before splitting, so the
        deny-list matches Windows-style and POSIX-style strings alike.

        Args:
            norm (str): Already-normalized path (from _norm()).

        Returns:
            tuple[str, str]: (parent, basename) - parent is "" for bare names.
        """
        canon = _canon(norm)
        if "\\" in canon:
            parent, _, name = canon.rpartition("\\")
            return parent, name
        return "", canon

    def _under_critical_tree(self, norm: str, is_dir: bool) -> bool:
        """Check whether `norm` falls inside an OS binary tree.

        Files inside explicitly cleanable sub-trees (LogFiles,
        spool PRINTERS, winevt Logs) are exempt; folder targets are
        never exempt - the folders themselves must survive.

        Args:
            norm (str): Normalized path to check.
            is_dir (bool): True for folder targets (no exemptions apply).

        Returns:
            bool: True when the target is inside a critical tree.
        """
        canon = _canon(norm)
        for tree in self._critical_tree_roots():
            if canon.startswith(tree + "\\"):
                rel = canon[len(tree) + 1:]
                exempt = (not is_dir
                          and rel.startswith(_TREE_FILE_EXEMPT_PREFIXES))
                return not exempt
        return False

    def _is_critical_file_target(self, norm: str) -> bool:
        """Lote D5 gate for FILE targets (string checks only, no syscalls).

        Refuses: deny-listed basenames anywhere, loose files directly
        under the Windows directory, and files inside the OS binary
        trees (except the whitelisted cleanable sub-trees).

        Args:
            norm (str): Normalized path (from _norm()).

        Returns:
            bool: True when this file must never be deleted.
        """
        parent, name = self._deny_parts(norm)
        if name in _CRITICAL_FILE_NAMES:
            return True
        self._critical_tree_roots()  # ensures self._windows_dir is set
        if parent and parent == self._windows_dir:
            # Loose files directly under C:\Windows are OS-owned
            # (explorer.exe, win.ini, ...): never cleaning targets.
            return True
        return self._under_critical_tree(norm, is_dir=False)

    def _is_critical_folder_target(self, norm: str) -> bool:
        """Lote D5 gate for FOLDER targets.

        Same refusal rules as files but without sub-tree exemptions:
        a folder inside System32/SysWOW64/Boot is never removable, and
        neither is a folder directly under the Windows directory.

        Args:
            norm (str): Normalized path (from _norm()).

        Returns:
            bool: True when this folder must never be deleted.
        """
        parent, name = self._deny_parts(norm)
        if name in _CRITICAL_FILE_NAMES:
            return True
        self._critical_tree_roots()
        if parent and parent == self._windows_dir:
            return True
        return self._under_critical_tree(norm, is_dir=True)

    # ------------------------------------------------------------ policy

    @staticmethod
    def is_drive_root(path: str) -> bool:
        """Check if a path is exactly a drive root like 'C:\\\\'.
        
        Drive roots are always refused as deletion targets to prevent
        accidental formatting of entire drives.
        
        Args:
            path (str): Path to check (may contain %ENV% variables).
            
        Returns:
            bool: True if the path is a drive root (e.g., "C:\\\\", "D:/"),
                  False otherwise.
                  
        Example:
            >>> SafetyGuard.is_drive_root("C:\\\\")
            True
            >>> SafetyGuard.is_drive_root("C:\\\\Windows")
            False
        """
        drive, tail = os.path.splitdrive(
            os.path.normpath(os.path.expandvars(path)))
        return bool(drive) and tail in ("\\", "/", "")

    @staticmethod
    def _norm(path: str) -> str:
        """Normalize a path: expand env vars, absolutize, normalize case and separators.
        
        This is the standard normalization used for all path comparisons.
        It ensures that paths are compared consistently regardless of
        case, separator style, or environment variable expansion.
        
        Args:
            path (str): Path to normalize.
            
        Returns:
            str: Normalized path (lowercase on Windows, absolute, no redundant separators).
        """
        return os.path.normcase(os.path.normpath(os.path.expandvars(path)))

    def _parent_chain_is_clean(self, norm: str) -> bool:
        """Check if the parent directory chain of `norm` contains no junction/reparse point.
        
        realpath resolves junctions, so comparing it with the plain normalized
        parent is the check. This is memoized per parent because thousands of
        file targets share the same parents, making this a critical performance
        optimization.
        
        Args:
            norm (str): Normalized path (from _norm()).
            
        Returns:
            bool: True if the parent directory chain has no junctions, False otherwise.
            
        Notes:
            - Memoization: Results are cached in self._parent_clean
              (OrderedDict). Hits are refreshed to the recency end; when
              the cap is reached the SINGLE OLDEST entry is evicted (LRU,
              E3.1) instead of clearing the whole cache, which used to
              collapse the hit-rate on large winapp2 cleans.
            - Thread-safety: same profile as before — single GIL-atomic
              dict operations, no cross-thread invariant beyond "values
              are pure functions of the path".
        """
        parent = os.path.dirname(norm)
        cached = self._parent_clean.get(parent)
        if cached is None:
            # Comparison must be normcase both sides; comparing a
            # normcased realpath to a raw parent fails on Windows when the
            # test uses POSIX "/dirs/..." style paths (E3, Windows).
            norm_parent = os.path.normcase(os.path.normpath(parent))
            cached = (os.path.normcase(os.path.normpath(
                os.path.realpath(parent))) == norm_parent)
            if len(self._parent_clean) >= _PARENT_CACHE_CAP:
                self._parent_clean.popitem(last=False)
            self._parent_clean[parent] = cached
        else:
            self._parent_clean.move_to_end(parent)
        return cached

    def _under_protected(self, norm: str) -> bool:
        """Check if `norm` is a protected user folder or one of its descendants.
        
        Args:
            norm (str): Normalized path (from _norm()).
            
        Returns:
            bool: True if the path is under a protected user folder, False otherwise.
        """
        roots = self.protected_user_roots()
        return any(norm == root or norm.startswith(root + os.sep)
                   for root in roots)

    def is_safe_delete_target(self, path: str,
                              is_dir: bool | None = None) -> bool:
        """Central gate: determine if `path` is safe to delete.
        
        This is the authority that all deletion operations must pass through.
        It returns False when `path` must never be deleted, and True when
        deletion is allowed.
        
        The `is_dir` parameter tells the gate how the caller intends to delete
        the target:
        - True = recursively as a folder (stricter rules)
        - False = a single file (more permissive)
        - None = inferred from the filesystem (conservative)
        
        The distinction matters: deleting a whole folder under Documents is
        refused while deleting individual files there is the cleanup itself.
        
        Args:
            path (str): Absolute path to check (may contain %ENV% variables).
            is_dir (bool | None, optional): Intent of deletion. True = folder,
                                            False = file, None = auto-detect.
                                            
        Returns:
            bool: True if the path is safe to delete, False if it must be refused.
            
        Policy Rules:
            1. Drive roots (C:\\\\) are always refused.
            2. Exact matches of system directories (C:\\Windows, Program Files)
               and environment roots (USERPROFILE, APPDATA) are refused.
            3. For file targets (is_dir=False):
               - Lote D5: OS-critical files (deny-listed basenames, loose
                 files directly under the Windows directory, files inside
                 System32/SysWOW64/Boot) are refused; cleanable sub-trees
                 (LogFiles, spool PRINTERS, winevt Logs) stay whitelisted.
               - Files anywhere else (including under protected folders) are
                 allowed IF the parent chain has no junctions.
               - Files reached *through* a junction into a protected area or
                 an OS binary tree are refused (realpath check).
            4. For folder targets (is_dir=True):
               - Lote D5: any folder inside System32/SysWOW64/Boot or
                 directly under the Windows directory is refused
                 (no exemptions).
               - The folder itself or any folder under a protected user folder
                 is refused (prevents recursive deletion of Documents, etc.).
               - Folders reached through a junction into a protected area are
                 refused (realpath check).
               
        Example:
            >>> guard = SafetyGuard()
            >>> guard.is_safe_delete_target("C:\\\\Windows\\\\Temp\\\\file.tmp", is_dir=False)
            True  # Individual file under Windows\\Temp is allowed
            >>> guard.is_safe_delete_target("C:\\\\Users\\\\John\\\\Documents", is_dir=True)
            False  # Folder under Documents is refused
            >>> guard.is_safe_delete_target("C:\\\\Users\\\\John\\\\Documents\\\\App\\\\logs\\\\cache.tmp", is_dir=False)
            True  # Individual file under Documents is allowed (that's the cleanup)
        """
        norm = self._norm(path)
        if self.is_drive_root(norm):
            return False
        if norm in self.exact_roots():
            return False
        if is_dir is None:
            try:
                is_dir = os.path.isdir(os.path.expandvars(path))
            except OSError:
                is_dir = True  # conservative: unknown targets are folders
        if not is_dir:
            # Lote D5: OS-critical files are refused before anything else
            # (deny-list basenames, loose Windows-dir children, binary trees).
            if self._is_critical_file_target(norm):
                return False
            # Single file: direct paths anywhere (including under
            # protected folders) are the cleanup itself. Only a file
            # reached *through* a junction into a protected area is
            # refused (its literal path looks harmless but resolves
            # inside the protected folder).
            if self._parent_chain_is_clean(norm):
                return True
            real = self._norm(os.path.realpath(os.path.expandvars(path)))
            # D5: a junction may resolve into an OS binary tree — the
            # resolved path gets the same deny-list treatment.
            if self._is_critical_file_target(real):
                return False
            return real == norm or not self._under_protected(real)
        # Folder target: refuse OS-critical trees first (D5), then the
        # folder itself or any folder under a protected user folder,
        # also when reached through a junction.
        if self._is_critical_folder_target(norm):
            return False
        real = self._norm(os.path.realpath(os.path.expandvars(path)))
        if self.is_drive_root(real) or real in self.exact_roots():
            return False
        if self._is_critical_folder_target(real):
            return False
        return not (self._under_protected(norm)
                    or self._under_protected(real))


_guard: SafetyGuard | None = None


def safety_guard() -> SafetyGuard:
    """Get the process-wide SafetyGuard singleton.
    
    This is the single source of truth for delete safety policy. All deletion
    operations should use this singleton to ensure consistent policy enforcement.
    
    Returns:
        SafetyGuard: The process-wide singleton instance.
    """
    global _guard
    if _guard is None:
        _guard = SafetyGuard()
    return _guard


def invalidate_safety_guard() -> None:
    """Force the singleton to recompute its root sets.
    
    Call this when the environment may have changed (e.g., in tests, or if
    the user profile is relocated). The next access will recompute the
    root sets from the current environment.
    """
    safety_guard().invalidate()


def is_safe_delete_target(path: str, is_dir: bool | None = None) -> bool:
    """Convenience wrapper around safety_guard() (backwards compatible
    with the old utils.is_safe_delete_target signature).
    
    This is the primary API for checking delete safety. It delegates to
    the singleton SafetyGuard instance.
    
    Args:
        path (str): Absolute path to check.
        is_dir (bool | None, optional): Intent of deletion. True = folder,
                                        False = file, None = auto-detect.
                                        
    Returns:
        bool: True if the path is safe to delete, False if it must be refused.
        
    Example:
        >>> is_safe_delete_target("C:\\\\Temp\\\\file.tmp", is_dir=False)
        True
        >>> is_safe_delete_target("C:\\\\Users\\\\John\\\\Documents", is_dir=True)
        False
    """
    return safety_guard().is_safe_delete_target(path, is_dir)
