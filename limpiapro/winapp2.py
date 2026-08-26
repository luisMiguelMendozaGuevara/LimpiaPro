"""Parser for the winapp2.ini format with detection and exclusions.

The winapp2.ini format is a community-maintained database of cleaning rules
for thousands of applications. This module implements a robust parser that
handles the subset of features used by LimpiaPro:

Supported Format:
    [Application]
    Detect=HKCU\\Software\\Something      (singular condition, for compat)
    Detect1=HKLM\\...                    (indexed: ALL must be true)
    DetectFile1=%LocalAppData%\\Something*  (file detect, wildcards allowed)
    SpecialDetect=DET_XXX                (CCleaner-internal: discarded)
    FileKey1=path|mask[;mask...]|RECURSE|REMOVESELF
    ExcludeKey1=path|mask[;mask...]      (protects files from deletion)

Architecture Overview:
    - **Two-pass parsing**: First pass accumulates FileKeys and ExcludeKeys,
      second pass builds WinAppRule objects (a rule needs all the ExcludeKeys
      of its section).
    - **Detection separation**: Detection logic (registry/file checks) is
      separated from parsing, allowing the parser to be tested without
      touching the registry or disk.
    - **Lazy regex compilation**: WinAppRule.patterns_re compiles masks as
      regexes on first access, avoiding startup overhead for inactive rules.
    - **Memoized detection**: detect_true() caches results to avoid redundant
      registry/file checks (thousands of sections repeat the same conditions).

Performance Optimizations:
    - Regex compilation: Patterns are compiled lazily (only detected apps are scanned).
    - Detection memoization: Same conditions are checked only once per process.
    - Normalization: Roots are normalized once in CleanCategory._rule_roots(),
      avoiding repeated GetFullPathName syscalls per file.

Safety Integration:
    - ExcludeKey: Protects specific files/folders from deletion even if they
      match FileKey patterns.
    - REMOVESELF: Removes the rule's root folder if it's empty after cleaning.
      Respects the safety layer (cannot remove protected roots).
"""

import fnmatch
import os
import re
import winreg
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Optional

from .utils import glob_like

# Windows registry hive mappings for Detect= conditions.
_HIVES = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKU": winreg.HKEY_USERS,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
}

# Regex pattern for matching Detect/DetectFile keys (with optional index).
_DETECT_RE = re.compile(r"^(detect|detectfile)\d*$", re.IGNORECASE)

# Sections whose FileKeys target user credentials or personal data.
# The community winapp2.ini ships them for people who want that scrubbing,
# but LimpiaPro's winapp2 category is one all-or-nothing checkbox, so
# deleting saved passwords / autofill / history alongside temp files is a
# silent data-loss hazard. These sections are excluded by default.
SENSITIVE_SECTION_RE = re.compile(
    r"password|autofill|browsing history|web browsing session|bookmark",
    re.IGNORECASE)


def _split_masks(masks: str) -> list:
    """Split a mask string into individual masks (separated by ; or ,).
    
    Handles the DOS-style "*.*" wildcard (any file, with or without extension)
    by converting it to "*". Empty mask lists default to ["*"] (match everything).
    
    Args:
        masks (str): Mask string (e.g., "*.tmp;*.log" or "*.tmp,*.log").
        
    Returns:
        list[str]: List of individual mask patterns. Defaults to ["*"] if empty.
        
    Example:
        >>> _split_masks("*.tmp;*.log")
        ['*.tmp', '*.log']
        >>> _split_masks("*.*")
        ['*']
        >>> _split_masks("")
        ['*']
    """
    out = []
    for m in masks.replace(";", ",").split(","):
        m = m.strip()
        if m == "*.*":
            m = "*"  # DOS semantics: any file, with or without extension
        if m:
            out.append(m)
    return out or ["*"]


class ExcludeKey:
    """File exclusion: whatever matches (root, masks) is not deleted.
    
    ExcludeKey protects specific files or folders from deletion even if they
    match a FileKey pattern. This is critical for preserving important files
    within application directories.
    
    Supported Variants:
        - **root|masks**: Excludes files matching masks in the root folder.
        - **root\\*|masks**: Excludes files matching masks recursively under root.
        - **FILE|path**: Excludes one exact file path.
        - **REG|...**: Ignored (the app does not delete registry data from winapp2 rules).
    
    Attributes:
        root (str): Normalized, absolute path of the exclusion root (empty for FILE variant).
        patterns (tuple[str]): Tuple of mask patterns (e.g., ("*.tmp", "*.log")).
        recursive (bool): If True, apply exclusion recursively under root.
        exact (str | None): Normalized, absolute path for FILE variant exclusions.
    """

    __slots__ = ("exact", "patterns", "recursive", "root")

    def __init__(self, root: str = "", patterns=("*",),
                 recursive: bool = False, exact: str | None = None):
        """Initialize an ExcludeKey instance.
        
        Args:
            root (str, optional): Root path for the exclusion (normalized with normcase+abspath).
                                  Empty string for FILE variant.
            patterns (tuple[str], optional): Tuple of mask patterns. Defaults to ("*",).
            recursive (bool, optional): If True, apply recursively. Defaults to False.
            exact (str | None, optional): Exact file path for FILE variant (normalized).
        """
        self.root = os.path.normcase(os.path.abspath(root)) if root else ""
        self.patterns = tuple(patterns)
        self.recursive = recursive
        self.exact = (os.path.normcase(os.path.abspath(exact))
                      if exact else None)

    @classmethod
    def parse(cls, val: str) -> Optional["ExcludeKey"]:
        """Parse an ExcludeKey value into an ExcludeKey instance.
        
        Handles the three supported variants: FILE|path, root|masks, and root\\*|masks.
        Returns None for REG variants and malformed input.
        
        Args:
            val (str): ExcludeKey value string (e.g., "FILE|C:\\path\\file.tmp").
            
        Returns:
            Optional[ExcludeKey]: Parsed ExcludeKey instance, or None if invalid/REG.
            
        Example:
            >>> ExcludeKey.parse("FILE|%APPDATA%\\App\\important.dat")
            ExcludeKey(root='', patterns=('*',), recursive=False, exact='c:\\users\\john\\appdata\\roaming\\app\\important.dat')
            >>> ExcludeKey.parse("%TEMP%\\App|*.log")
            ExcludeKey(root='c:\\users\\john\\appdata\\local\\temp\\app', patterns=('*.log',), recursive=False, exact=None)
        """
        parts = [p.strip() for p in val.split("|")]
        if not parts or not parts[0]:
            return None
        head = parts[0]
        if head.upper() == "REG":
            return None
        if head.upper() == "FILE" and len(parts) >= 2:
            exact = os.path.expandvars(parts[1])
            return cls(exact=exact) if exact else None
        root = os.path.expandvars(head)
        masks = parts[1] if len(parts) > 1 else ""
        recursive = root.endswith("\\*") or root.endswith("/*")
        if recursive:
            root = root[:-2]
        return cls(root=root, patterns=_split_masks(masks), recursive=recursive)

    def matches(self, path: str) -> bool:
        """Check if a path is protected by this exclusion.
        
        Args:
            path (str): Normalized, absolute path to check (already normalized with
                       normcase+abspath by CleanCategory._rule_roots).
                       
        Returns:
            bool: True if the path is protected by this exclusion, False otherwise.
            
        Notes:
            - FILE variant: Exact match only.
            - root|masks: Matches if parent == root and filename matches any pattern.
            - root\\*|masks: Matches if parent is under root (recursively) and filename
              matches any pattern.
            - Performance: Expects path to already be normalized to avoid redundant
              GetFullPathName calls.
        """
        if self.exact is not None:
            return path == self.exact
        if not self.root:
            return False
        parent = os.path.dirname(path)
        name = os.path.basename(path)
        if self.recursive:
            inside = parent == self.root or parent.startswith(self.root + os.sep)
        else:
            inside = parent == self.root
        if not inside:
            return False
        return any(fnmatch.fnmatch(name, p) for p in self.patterns)


class WinAppRule:
    """One deletion rule (FileKey) with its masks, recursion flag and section exclusions.
    
    This represents a single FileKey directive from winapp2.ini, specifying:
    - The root path to scan for files to delete.
    - The mask patterns to match (e.g., "*.tmp", "*.log").
    - Whether to recurse into subdirectories (RECURSE flag).
    - Whether to remove the root folder if empty after cleaning (REMOVESELF flag).
    - The section's ExcludeKeys that protect specific files from deletion.
    
    Performance Optimization:
        patterns_re holds the masks precompiled as case-insensitive regexes
        (fnmatch.translate), so matching a file does not re-enter fnmatch
        per pattern — the winapp scan matches tens of thousands of files
        against thousands of patterns (measured hotspot). The regexes compile
        lazily: the parser builds a rule for every FileKey in winapp2.ini
        (~14k), but only detected apps are scanned, so compiling eagerly
        wastes startup time on inactive rules.
    
    Attributes:
        root (str): Root path to scan (may contain %ENV% variables).
        recurse (bool): If True, scan subdirectories recursively.
        patterns (tuple[str]): Tuple of mask patterns (e.g., ("*.tmp", "*.log")).
        patterns_lower (tuple[str]): Lowercase versions of patterns for fast matching.
        _patterns_re (tuple[re.Pattern] | None): Lazy-compiled regex patterns.
        remove_self (bool): If True, remove the root folder if empty after cleaning.
        excludes (tuple[ExcludeKey]): Tuple of ExcludeKey objects from the section.
    """

    __slots__ = (
        "_patterns_re",
        "excludes",
        "patterns",
        "patterns_lower",
        "recurse",
        "remove_self",
        "root",
    )

    def __init__(self, root: str, recurse: bool = False,
                 patterns=("*",), remove_self: bool = False,
                 excludes: Sequence = ()):
        """Initialize a WinAppRule instance.
        
        Args:
            root (str): Root path to scan (may contain %ENV% variables).
            recurse (bool, optional): If True, scan recursively. Defaults to False.
            patterns (tuple[str], optional): Mask patterns. Defaults to ("*",).
            remove_self (bool, optional): If True, remove root if empty. Defaults to False.
            excludes (Sequence[ExcludeKey], optional): ExcludeKey objects. Defaults to ().
        """
        self.root = root
        self.recurse = recurse
        self.patterns = tuple(patterns)
        self.patterns_lower = tuple(p.lower() for p in self.patterns)
        self._patterns_re = None
        self.remove_self = remove_self
        self.excludes = tuple(excludes)

    @property
    def patterns_re(self):
        """Compiled case-insensitive regexes for self.patterns (lazy compilation).
        
        This property compiles the mask patterns into regex patterns on first
        access, caching the result for subsequent calls. This avoids the
        overhead of compiling regexes for thousands of inactive rules at startup.
        
        Returns:
            tuple[re.Pattern]: Tuple of compiled, case-insensitive regex patterns.
        """
        if self._patterns_re is None:
            self._patterns_re = tuple(
                re.compile(fnmatch.translate(p), re.IGNORECASE)
                for p in self.patterns)
        return self._patterns_re

    def is_excluded(self, path: str) -> bool:
        """Check if a path is protected by any ExcludeKey in this rule.
        
        Args:
            path (str): Path to check (already absolutized by CleanCategory._rule_roots,
                       so normcase is enough here to avoid one GetFullPathName call per file).
                       
        Returns:
            bool: True if the path is protected by any ExcludeKey, False otherwise.
        """
        if not self.excludes:
            return False
        # Roots are already absolutized (normcase+abspath) by
        # CleanCategory._rule_roots, so normcase is enough here: it avoids
        # one GetFullPathName call per file.
        norm = os.path.normcase(path)
        return any(ex.matches(norm) for ex in self.excludes)


def _parse_filekey(val: str, excludes) -> WinAppRule | None:
    """Parse a FileKey value into a WinAppRule instance.
    
    Handles the FileKey format: path|masks|OPTION, where OPTION is RECURSE
    or REMOVESELF. A path ending in \\* also marks recursion ('*' cannot be
    part of a real folder name on Windows).
    
    Args:
        val (str): FileKey value string (e.g., "%TEMP%\\App|*.tmp;*.log|RECURSE").
        excludes (Sequence[ExcludeKey]): ExcludeKey objects from the section.
        
    Returns:
        WinAppRule | None: Parsed WinAppRule instance, or None if invalid/empty.
        
    Example:
        >>> rule = _parse_filekey("%TEMP%\\App|*.tmp|RECURSE", [])
        >>> rule.root
        '%TEMP%\\App'
        >>> rule.recurse
        True
        >>> rule.patterns
        ('*.tmp',)
    """
    parts = [p.strip() for p in val.split("|")]
    root = parts[0] if parts else ""
    if not root:
        return None
    star_tail = root.endswith("\\*") or root.endswith("/*")
    if star_tail:
        root = root[:-2]
    masks = parts[1] if len(parts) > 1 else ""
    option = parts[2] if len(parts) > 2 else ""
    # tolerate 'path|RECURSE' without masks
    if masks.upper() in ("RECURSE", "REMOVESELF") and not option:
        option = masks
        masks = ""
    recurse = option.lower() == "recurse" or star_tail
    remove_self = option.lower() == "removeself"
    return WinAppRule(root, recurse=recurse, patterns=_split_masks(masks),
                      remove_self=remove_self, excludes=excludes)


@dataclass
class WinAppSection:
    """One parsed [App] section of winapp2.ini.
    
    Represents a single application section with its detection conditions,
    special flags, and cleaning rules. Replaces the string-keyed dicts of
    the old parse_sections; rules carry their section's ExcludeKeys already
    applied.
    
    Attributes:
        name (str): Application name (from [Application] header).
        detects (list[str]): List of Detect=/DetectFile= condition strings.
        special (bool): True if the section has SpecialDetect (CCleaner-internal, discarded).
        rules (list[WinAppRule]): List of FileKey rules for this section.
    """
    name: str
    detects: list[str] = field(default_factory=list)
    special: bool = False
    rules: list[WinAppRule] = field(default_factory=list)


def _parse_sections(text: str) -> list[WinAppSection]:
    """Two-pass parsing of winapp2.ini text into WinAppSection objects.
    
    First pass: Accumulate FileKeys and ExcludeKeys for each section.
    Second pass: Build WinAppRule objects (a rule needs all the ExcludeKeys
    of its section, so they must be collected first).
    
    Args:
        text (str): Full text content of the winapp2.ini file.
        
    Returns:
        list[WinAppSection]: List of parsed sections with rules attached.
        
    Notes:
        - Comments: Lines starting with ; or # are ignored.
        - Empty lines: Ignored.
        - Malformed lines: Silently skipped (no "=" or empty key/value).
        - SpecialDetect: Marks the section as special (CCleaner-internal, discarded).
    """
    sections = []
    current = None
    pending = {}  # section id -> {filekeys, excludes}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            name = line[1:-1].strip()
            if name:
                current = WinAppSection(name=name)
                sections.append(current)
                pending[id(current)] = {"filekeys": [], "excludes": []}
            continue
        if current is None or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if not key or not val:
            continue
        low = key.lower()
        if low.startswith("filekey"):
            pending[id(current)]["filekeys"].append(val)
        elif low.startswith("excludekey"):
            ex = ExcludeKey.parse(val)
            if ex is not None:
                pending[id(current)]["excludes"].append(ex)
        elif _DETECT_RE.match(low):
            current.detects.append(val)
        elif low == "specialdetect":
            current.special = True
    for s in sections:
        data = pending[id(s)]
        rules = []
        for fk in data["filekeys"]:
            rule = _parse_filekey(fk, data["excludes"])
            if rule is not None:
                rules.append(rule)
        s.rules = rules
    return sections


def parse_sections(text: str) -> list[WinAppSection]:
    """Parse the text of a winapp2.ini into sections (detection not checked).
    
    This is the public API for parsing winapp2.ini content without running
    detection checks. Useful for testing or analyzing the file structure.
    
    Args:
        text (str): Full text content of the winapp2.ini file.
        
    Returns:
        list[WinAppSection]: List of parsed sections with rules attached.
    """
    return _parse_sections(text)


_DETECT_CACHE = {}


def invalidate_detect_cache():
    """Drop every cached Detect= result.
    
    Called when a different winapp2.ini is loaded: conditions memoized
    from the previous file (or an older install state) must not be reused
    for the new file. This prevents false positives/negatives when the
    user loads a custom winapp2.ini.
    """
    _DETECT_CACHE.clear()


def detect_true(condition: str) -> bool:
    """Check a winapp2 Detect=/DetectFile= condition (memoized).
    
    The thousands of sections in winapp2 repeat the same conditions (same
    hive + subkey) very often, and the result does not change during the
    process lifetime. This function caches results to avoid redundant
    registry/file checks.
    
    Args:
        condition (str): Detect condition string (e.g., "HKCU\\Software\\App"
                        or "FILE|%APPDATA%\\App\\file.dat").
                        
    Returns:
        bool: True if the condition is satisfied (app is installed), False otherwise.
        
    Notes:
        - Empty condition: Returns True (no detection required).
        - Memoization: Results are cached in _DETECT_CACHE dict.
        - Thread safety: Not thread-safe, but detection runs on a single worker thread.
    """
    d = (condition or "").strip()
    if not d:
        return True
    cached = _DETECT_CACHE.get(d)
    if cached is not None:
        return cached
    result = _detect_true(d)
    _DETECT_CACHE[d] = result
    return result


def _detect_true(d: str) -> bool:
    """Uncached check of one condition (registry key exists / file path or glob exists).
    
    This is the internal implementation that actually checks the registry
    or filesystem. It's called by detect_true() on cache misses.
    
    Args:
        d (str): Detect condition string.
        
    Returns:
        bool: True if the condition is satisfied, False otherwise.
        
    Supported Conditions:
        - Registry: "HKCU\\Software\\App" (checks if the key exists).
        - File: "%APPDATA%\\App\\file.dat" (checks if the file exists).
        - Glob: "%APPDATA%\\App\\*.dat" (checks if any file matches).
        - FILE prefix: "FILE|%APPDATA%\\App\\file.dat" (strips FILE prefix).
        
    Notes:
        - Error handling: Returns False on any exception (registry access denied,
          file not found, etc.).
        - Environment variables: Expanded with os.path.expandvars().
        - Glob patterns: Expanded with glob_like().
    """
    try:
        low = d.lower()
        if low.startswith("file"):
            d = d[len("file"):].strip()
        if "\\" in d:
            hive_name, sub = d.split("\\", 1)
            hive = _HIVES.get(hive_name.upper())
            if hive is not None:
                try:
                    with winreg.OpenKey(hive, os.path.expandvars(sub)):
                        return True
                except OSError:
                    return False
        d = os.path.expandvars(d)
        return any(os.path.exists(h) for h in glob_like(d))
    except Exception:
        return False


def active_sections(sections) -> list[WinAppSection]:
    """Filter the sections whose detection passes (apps detected as installed).
    
    Several Detect/Detect1..N conditions combine with AND (winapp2 format):
    the section only applies when ALL of them are true. Sections with only
    SpecialDetect (CCleaner-internal) are discarded.
    
    Args:
        sections (list[WinAppSection]): List of parsed sections to filter.
        
    Returns:
        list[WinAppSection]: List of sections that passed detection (installed apps).
        
    Notes:
        - AND logic: All Detect conditions must be true for the section to be active.
        - SpecialDetect: Sections with only SpecialDetect are discarded.
        - Empty rules: Sections with no FileKey rules are discarded.
    """
    out = []
    for s in sections:
        if not s.rules:
            continue
        if s.special and not s.detects:
            continue
        if all(detect_true(d) for d in s.detects):
            out.append(s)
    return out


def default_winapp_file() -> str:
    """Get the path of the bundled winapp2.ini inside the app bundle.

    Returns:
        str: Absolute path to the bundled winapp2.ini file.

    Notes:
        - Works in development (project root) and packaged (PyInstaller's
          _MEIPASS: the bundle carries its data, whatever folder the exe
          lives in).
    """
    from .utils import data_dir
    return os.path.join(data_dir(), "winapp2.ini")


def parse_winapp_rules(path: str,
                       exclude_sensitive: bool = True) -> list[WinAppSection]:
    """Parse a winapp2.ini file and return the active sections (apps detected as installed).

    This is the primary API for loading winapp2.ini rules. It reads the file,
    parses it, runs detection checks, and returns only the sections for
    installed applications.

    Args:
        path (str): Absolute path to the winapp2.ini file.
        exclude_sensitive (bool): When True (the default), sections whose
            name matches SENSITIVE_SECTION_RE (saved passwords, autofill,
            browsing history, session restore, bookmark data) are dropped:
            the winapp2 category is a single checkbox, and silently deleting
            credentials/history with it is an unacceptable data-loss risk.

    Returns:
        list[WinAppSection]: List of active sections (detected apps) with rules.
                             Empty list if the file doesn't exist or can't be read.

    Notes:
        - Encoding: Reads with utf-8-sig encoding (handles BOM) with errors="replace".
        - Error handling: Returns empty list on OSError (file not found, permission denied).
        - Detection: Runs detect_true() for each section's conditions.
    """
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    sections = parse_sections(text)
    if exclude_sensitive:
        sections = [s for s in sections
                    if not SENSITIVE_SECTION_RE.search(s.name)]
    return active_sections(sections)
