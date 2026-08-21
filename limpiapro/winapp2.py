"""Parser for the winapp2.ini format with detection and exclusions.

Supported subset:
  [Application]
  Detect=HKCU\\Software\\Something      (singular condition, for compat)
  Detect1=HKLM\\...                    (indexed: ALL must be true)
  DetectFile1=%LocalAppData%\\Something*  (file detect, wildcards allowed)
  SpecialDetect=DET_XXX                (CCleaner-internal: discarded)
  FileKey1=path|mask[;mask...]|RECURSE|REMOVESELF
  ExcludeKey1=path|mask[;mask...]      (protects files from deletion)

Detection is kept separate from parsing so the parser can be tested
without touching the registry or the disk."""

import fnmatch
import os
import re
import winreg
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Optional

from .utils import app_dir, glob_like

_HIVES = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
    "HKU": winreg.HKEY_USERS,
    "HKCR": winreg.HKEY_CLASSES_ROOT,
}

_DETECT_RE = re.compile(r"^(detect|detectfile)\d*$", re.IGNORECASE)


def _split_masks(masks: str) -> list:
    """List of masks separated by ; or , (empty = everything)."""
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

    A root ending in '\\*' excludes recursively. The 'FILE|path' variant
    excludes one exact file; 'REG|...' is ignored because the app does not
    delete registry data from winapp2 rules."""

    __slots__ = ("root", "patterns", "recursive", "exact")

    def __init__(self, root: str = "", patterns=("*",),
                 recursive: bool = False, exact: str | None = None):
        self.root = os.path.normcase(os.path.abspath(root)) if root else ""
        self.patterns = tuple(patterns)
        self.recursive = recursive
        self.exact = (os.path.normcase(os.path.abspath(exact))
                      if exact else None)

    @classmethod
    def parse(cls, val: str) -> Optional["ExcludeKey"]:
        """Parse an ExcludeKey value ('FILE|path', 'root|masks' or
        'root\\*|masks'); None for REG variants and malformed input."""
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
        """True when `path` (already normalized with normcase+abspath) is
        protected by this exclusion."""
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
    """One deletion rule (FileKey) with its masks, recursion flag and
    section exclusions. patterns_re holds the masks precompiled as
    case-insensitive regexes (fnmatch.translate), so matching a file does
    not re-enter fnmatch per pattern — the winapp scan matches tens of
    thousands of files against thousands of patterns (measured hotspot).

    The regexes compile lazily: the parser builds a rule for every
    FileKey in winapp2.ini (~14k), but only detected apps are scanned,
    so compiling eagerly wastes startup time on inactive rules."""

    __slots__ = ("root", "recurse", "patterns", "patterns_lower",
                 "_patterns_re", "remove_self", "excludes")

    def __init__(self, root: str, recurse: bool = False,
                 patterns=("*",), remove_self: bool = False,
                 excludes: Sequence = ()):
        self.root = root
        self.recurse = recurse
        self.patterns = tuple(patterns)
        self.patterns_lower = tuple(p.lower() for p in self.patterns)
        self._patterns_re = None
        self.remove_self = remove_self
        self.excludes = tuple(excludes)

    @property
    def patterns_re(self):
        """Compiled case-insensitive regexes for self.patterns (lazy)."""
        if self._patterns_re is None:
            self._patterns_re = tuple(
                re.compile(fnmatch.translate(p), re.IGNORECASE)
                for p in self.patterns)
        return self._patterns_re

    def is_excluded(self, path: str) -> bool:
        """True when any ExcludeKey protects `path`."""
        if not self.excludes:
            return False
        # Roots are already absolutized (normcase+abspath) by
        # CleanCategory._rule_roots, so normcase is enough here: it avoids
        # one GetFullPathName call per file.
        norm = os.path.normcase(path)
        return any(ex.matches(norm) for ex in self.excludes)


def _parse_filekey(val: str, excludes) -> WinAppRule | None:
    """Parse 'path|masks|OPTION' (OPTION: RECURSE or REMOVESELF).

    A path ending in '\\*' also marks recursion ('*' cannot be part of a
    real folder name on Windows)."""
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

    Replaces the string-keyed dicts of the old parse_sections; rules
    carry their section's ExcludeKeys already applied."""
    name: str
    detects: list[str] = field(default_factory=list)
    special: bool = False
    rules: list[WinAppRule] = field(default_factory=list)


def _parse_sections(text: str) -> list[WinAppSection]:
    """Two-pass parsing: first accumulate filekeys/excludes, then build
    the rules (a rule needs all the ExcludeKeys of its section)."""
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
    """Parse the text of a winapp2.ini into sections (detection not
    checked). Returns a list of WinAppSection."""
    return _parse_sections(text)


_DETECT_CACHE = {}


def invalidate_detect_cache():
    """Drop every cached Detect= result.

    Called when a different winapp2.ini is loaded: conditions memoized
    from the previous file (or an older install state) must not be reused
    for the new file."""
    _DETECT_CACHE.clear()


def detect_true(condition: str) -> bool:
    """Check a winapp2 Detect=/DetectFile= condition.

    Memoized: the thousands of sections in winapp2 repeat the same
    conditions (same hive + subkey) very often, and the result does not
    change during the process lifetime."""
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
    """Uncached check of one condition (registry key exists / file
    path or glob exists)."""
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
    """Filter the sections whose detection passes.

    Several Detect/Detect1..N conditions combine with AND (winapp2
    format): the section only applies when ALL of them are true. Sections
    with only SpecialDetect (CCleaner-internal) are discarded."""
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
    """Path of the bundled winapp2.ini next to the app."""
    return os.path.join(app_dir(), "winapp2.ini")


def parse_winapp_rules(path: str) -> list[WinAppSection]:
    """Parse a winapp2.ini file and return the active sections (apps
    detected as installed): a list of WinAppSection."""
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    return active_sections(parse_sections(text))
