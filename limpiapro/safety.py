"""Central delete-safety policy (SafetyGuard).

Every destructive operation in LimpiaPro passes through this gate
immediately before touching the filesystem. Policy:

  * Exact refusal — drive roots, system directories (C:\\Windows,
    Program Files, ...), environment roots (USERPROFILE, APPDATA, ...)
    and the well-known user folders (Desktop, Documents, Downloads,
    Music, Pictures, Videos, ...) can never be deletion targets.

  * Descendant refusal (folder targets only) — a *folder* that lives
    under a protected user folder can never be removed recursively
    (the reported "Documents" incident is exactly this class of bug:
    a descendant folder passed the old exact-match gate and was
    rmtree'd whole). Individual *files* anywhere stay cleanable: that
    is the cleanup itself, and winapp2 legitimately removes files under
    e.g. %UserProfile%\\Documents\\App\\logs.

  * Reparse points / junctions — the real final path (os.path.realpath,
    which resolves junctions on Windows) is checked, so a target
    reached *through* a junction that resolves into a protected area
    is refused even when the literal path looks harmless. Walks in
    categories.py / utils.iter_file_sizes never descend into junctions.

The old flat helper `is_safe_delete_target(path)` in utils.py remains as
a thin wrapper (tests and categories import it from there); the policy
lives here so the UI can never bypass it.
"""

from __future__ import annotations

import ctypes
import os
import re
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
_FOLDERID_ONEDRIVE = "{A52BBA46-E9E1-435F-B3D9-28DAA648C0F6}"

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
_PARENT_CACHE_CAP = 4096


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _parse_guid(text: str) -> _GUID:
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
    """Real location of a Windows known folder (redirection-aware), or
    None when the API is unavailable (non-Windows, restricted, ...)."""
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
            try:
                ctypes.windll.ole32.CoTaskMemFree(out)
            except Exception:
                pass
        if hr == 0 and path:
            return path
    except Exception:
        pass
    return None


class SafetyGuard:
    """Central delete-safety policy (see module docstring).

    Root sets are computed lazily and cached; call invalidate() when the
    environment may have changed (tests, ...)."""

    def __init__(self) -> None:
        self._exact_roots: frozenset[str] | None = None
        self._user_roots: frozenset[str] | None = None
        # parent dir (normcased) -> True when its chain has no junction.
        self._parent_clean: dict[str, bool] = {}

    # ------------------------------------------------------------- roots

    def invalidate(self) -> None:
        """Drop cached root sets (env / known folders may have changed)."""
        self._exact_roots = None
        self._user_roots = None
        self._parent_clean.clear()

    def exact_roots(self) -> frozenset[str]:
        """System dirs + environment roots: refused as exact targets."""
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
        """Well-known user folders (real locations + %USERPROFILE%
        fallbacks): refused as targets and as ancestors of folder targets."""
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

    # ------------------------------------------------------------ policy

    @staticmethod
    def is_drive_root(path: str) -> bool:
        """True when `path` is exactly a drive root like 'C:\\'."""
        drive, tail = os.path.splitdrive(
            os.path.normpath(os.path.expandvars(path)))
        return bool(drive) and tail in ("\\", "/", "")

    @staticmethod
    def _norm(path: str) -> str:
        """Expand env vars, absolutize, normalize case and separators."""
        return os.path.normcase(os.path.normpath(os.path.expandvars(path)))

    def _parent_chain_is_clean(self, norm: str) -> bool:
        """True when the parent directory chain of `norm` contains no
        junction/reparse point. realpath resolves junctions, so comparing
        it with the plain normalized parent is the check; memoized per
        parent because thousands of file targets share the same parents."""
        parent = os.path.dirname(norm)
        cached = self._parent_clean.get(parent)
        if cached is None:
            cached = (os.path.normcase(os.path.normpath(
                os.path.realpath(parent))) == parent)
            if len(self._parent_clean) >= _PARENT_CACHE_CAP:
                self._parent_clean.clear()
            self._parent_clean[parent] = cached
        return cached

    def _under_protected(self, norm: str) -> bool:
        """True when `norm` is a protected user folder or one of its
        descendants."""
        roots = self.protected_user_roots()
        for root in roots:
            if norm == root or norm.startswith(root + os.sep):
                return True
        return False

    def is_safe_delete_target(self, path: str,
                              is_dir: bool | None = None) -> bool:
        """Central gate: False when `path` must never be deleted.

        `is_dir` tells the gate how the caller intends to delete the
        target: True = recursively as a folder, False = a single file,
        None = inferred from the filesystem. The distinction matters:
        deleting a whole folder under Documents is refused while deleting
        individual files there is the cleanup itself."""
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
            # Single file: direct paths anywhere (including under
            # protected folders) are the cleanup itself. Only a file
            # reached *through* a junction into a protected area is
            # refused (its literal path looks harmless but resolves
            # inside the protected folder).
            if self._parent_chain_is_clean(norm):
                return True
            real = self._norm(os.path.realpath(os.path.expandvars(path)))
            return real == norm or not self._under_protected(real)
        # Folder target: refuse the folder itself or any folder under a
        # protected user folder, also when reached through a junction.
        real = self._norm(os.path.realpath(os.path.expandvars(path)))
        if self.is_drive_root(real) or real in self.exact_roots():
            return False
        return not (self._under_protected(norm)
                    or self._under_protected(real))


_guard: SafetyGuard | None = None


def safety_guard() -> SafetyGuard:
    """Process-wide SafetyGuard singleton."""
    global _guard
    if _guard is None:
        _guard = SafetyGuard()
    return _guard


def invalidate_safety_guard() -> None:
    """Force the singleton to recompute its root sets."""
    safety_guard().invalidate()


def is_safe_delete_target(path: str, is_dir: bool | None = None) -> bool:
    """Convenience wrapper around safety_guard() (backwards compatible
    with the old utils.is_safe_delete_target signature)."""
    return safety_guard().is_safe_delete_target(path, is_dir)
