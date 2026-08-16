"""Cleaning categories: system locations and winapp2 rules.

Each CleanCategory owns a list of locations (paths with %ENV% templates and
optional glob wildcards) or a set of parsed winapp2 rules. One single
traversal (_iter_targets) feeds scanning, preview listing and deletion, so
the same matching logic (masks, RECURSE, ExcludeKey) applies to all three.

Category labels and descriptions shown in the UI are translated through
i18n.t() keys ("cat.*")."""

import fnmatch
import os
import threading

from .i18n import t
from .utils import (PROGRESS_DELETE, PROGRESS_RULES, _delete_path,
                    _fast_folder_stats, _parallel_map, _safe_size, glob_like)
from .winapp2 import default_winapp_file, parse_winapp_rules


def user_dirs():
    """Cleaning locations as %ENV% templates (expanded on use, so they work
    for any user profile)."""
    return {
        "temp": r"%TEMP%",
        "win_temp": r"C:\Windows\Temp",
        "prefetch": r"C:\Windows\Prefetch",
        "recent": r"%APPDATA%\Microsoft\Windows\Recent",
        "explorer_cache": r"%LOCALAPPDATA%\Microsoft\Windows\Explorer",
        "edge": r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
        "chrome": r"%LOCALAPPDATA%\Google\Chrome\User Data",
        "brave": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data",
        "vivaldi": r"%LOCALAPPDATA%\Vivaldi\User Data",
        "opera": r"%APPDATA%\Opera Software\Opera Stable",
        "opera_gx": r"%APPDATA%\Opera Software\Opera GX Stable",
        "firefox": r"%APPDATA%\Mozilla\Firefox\Profiles",
        "update_cache": r"C:\Windows\SoftwareDistribution\Download",
        "cbs_logs": r"C:\Windows\Logs\CBS",
        "dump": r"%LOCALAPPDATA%\CrashDumps",
    }


def browser_cache_folders(base):
    """Cache folder candidates for every profile under a Chromium browser's
    User Data directory (the folders simply don't exist for profiles that
    never created them, so listing them all is cheap and safe)."""
    cache_folders = [
        "Cache", "Cache/Cache_Data", "Code Cache", "Code Cache/JS Cache",
        "GPUCache", "Service Worker/CacheStorage", "Service Worker/ScriptCache",
        "GrShaderCache", "ShaderCache", "DawnCache", "DawnGraphiteCache",
        "DawnWebGPUCache", "blob_storage", "CachedData",
    ]
    result = []
    if not os.path.isdir(base):
        return result
    try:
        for entry in os.listdir(base):
            p = os.path.join(base, entry)
            if not os.path.isdir(p):
                continue
            for cf in cache_folders:
                result.append(os.path.join(p, cf))
    except OSError:
        pass
    return result


class CleanCategory:
    """One cleaning category with its source locations or winapp2 rules.

    scan() measures (size, files) with os.scandir-based stats; list_files()
    yields the preview; clean() deletes the collected targets in parallel.
    `recycle_bin` categories are special-cased by the app (shell API)."""

    def __init__(self, key, label, description, locations, icon="\U0001F5D1"):
        self.key = key
        self.label = label
        self.description = description
        self.locations = locations
        self.icon = icon
        self.needs_admin = False
        self.recycle_bin = False
        self.rules = None
        self.size = 0
        self.files = 0
        self.errors = 0

    def _locations_existing(self):
        """Expand %ENV% vars and glob wildcards, keeping existing paths only."""
        out = []
        for loc in self.locations:
            for h in glob_like(os.path.expandvars(loc)):
                if os.path.exists(h):
                    out.append(h)
        return out

    @staticmethod
    def _match_name(name, patterns_lower):
        """Case-insensitive filename match against pre-lowered patterns.
        Empty pattern lists match everything."""
        if not patterns_lower:
            return True
        low = name.lower()
        for p in patterns_lower:
            if fnmatch.fnmatch(low, p):
                return True
        return False

    def _rule_roots(self):
        """Yield (rule, existing_root) for each winapp2 rule.

        The root is normalized and absolutized exactly once here:
        is_excluded() (winapp2) then receives absolute paths and only needs
        normcase, avoiding one GetFullPathName syscall per file."""
        for rule in self.rules or []:
            root = os.path.normcase(os.path.abspath(
                os.path.expandvars(rule.root)))
            if os.path.exists(root):
                yield rule, root

    def _iter_targets(self):
        """Iterate (rule_or_None, path) over everything the category would
        clean.

        One single traversal for scan, preview and deletion. Winapp2 rules
        apply masks, recursion and ExcludeKey exclusions; plain categories
        only touch the top level of each location (folders get removed
        whole when cleaning)."""
        if self.rules:
            for rule, root in self._rule_roots():
                if os.path.isfile(root):
                    if (self._match_name(os.path.basename(root), rule.patterns_lower)
                            and not rule.is_excluded(root)):
                        yield rule, root
                    continue
                for cur, dirs, fnames in os.walk(root):
                    if not rule.recurse:
                        dirs[:] = []
                    for name in fnames:
                        path = os.path.join(cur, name)
                        if (self._match_name(name, rule.patterns_lower)
                                and not rule.is_excluded(path)):
                            yield rule, path
        else:
            for loc in self._locations_existing():
                if os.path.isdir(loc):
                    try:
                        for name in os.listdir(loc):
                            yield None, os.path.join(loc, name)
                    except OSError:
                        pass
                else:
                    yield None, loc

    def _scan_rules(self, on_progress=None):
        """Scan winapp2-rule targets: measure each matched file/folder.

        Each category is scanned on its own thread; roots are walked
        serially inside it (extra parallelism gains nothing on a regular
        disk)."""
        self.size = 0
        self.files = 0
        for _rule, path in self._iter_targets():
            self.size += _safe_size(path)
            self.files += 1
            if on_progress and self.files % PROGRESS_RULES == 0:
                on_progress(self.files)
        return self.size

    def scan(self, on_progress=None):
        """Measure the category: total bytes and file count. Rule-based
        categories use _scan_rules; plain ones use the fast scandir stats."""
        if self.rules:
            return self._scan_rules(on_progress)
        self.size = 0
        self.files = 0
        for loc in self._locations_existing():
            if os.path.isdir(loc):
                size, files = _fast_folder_stats(loc, on_progress)
                self.size += size
                self.files += files
            else:
                self.files += 1
                try:
                    self.size += os.path.getsize(loc)
                except OSError:
                    pass
        return self.size

    def list_files(self, limit=1000):
        """Return (paths, scanned_count) for the preview dialog.

        The scanned count stops at the limit (`len(files) <= limit`), so it
        is not the real total number of targets."""
        files = []
        scanned = 0
        for _rule, path in self._iter_targets():
            scanned += 1
            files.append(path)
            if len(files) >= limit:
                break
        return files, scanned

    def clean(self, on_file=None, on_progress=None, target_bytes=0):
        """Delete every target of the category in parallel.

        Targets are collected in one pass and deleted through _parallel_map
        (plain categories only remove the top level of each location;
        folders are deleted whole with rmtree). Returns (removed, errors,
        freed_bytes).

        After cleaning there is no re-scan here: the UI re-analyzes
        everything when the cleanup finishes (analyze_all). Approximating
        until that refresh avoids one extra full traversal."""
        targets = []
        remove_roots = []
        for rule, path in self._iter_targets():
            targets.append(path)
            if rule is not None and rule.remove_self:
                root = os.path.abspath(os.path.expandvars(rule.root))
                if root not in remove_roots:
                    remove_roots.append(root)
        # Avoid double deletion when two rules/locations overlap.
        targets = list(dict.fromkeys(targets))
        if on_file:
            for target in targets:
                on_file(target)

        lock = threading.Lock()
        state = {"removed": 0, "errors": 0, "freed": 0, "done": 0}

        def _delete_one(target):
            size = _safe_size(target)
            ok = _delete_path(target)
            with lock:
                state["done"] += 1
                if ok:
                    state["removed"] += 1
                    state["freed"] += size
                else:
                    state["errors"] += 1
                done, freed = state["done"], state["freed"]
            # Chunked progress so the GUI is not flooded with after(0, ...).
            if on_progress and target_bytes > 0 and done % PROGRESS_DELETE == 0:
                on_progress(min(freed / target_bytes, 1.0))

        _parallel_map(_delete_one, targets)

        # REMOVESELF: remove the rule folder itself when left empty.
        for root in remove_roots:
            try:
                os.rmdir(root)
            except OSError:
                pass

        removed = state["removed"]
        errors = state["errors"]
        freed = state["freed"]
        self.size = max(0, self.size - freed)
        self.files = removed
        self.errors = errors
        return removed, errors, freed


def build_categories():
    """Build the default category set with translated labels/descriptions.

    Labels are resolved through i18n.t() at build time (the language is
    fixed at import, before any window exists)."""
    d = user_dirs()
    cats = []

    cat_temp = CleanCategory(
        "temp", t("cat.temp.label"), t("cat.temp.desc"),
        [d["temp"], d["win_temp"], d["prefetch"]], "\U0001F4DA")
    cat_temp.needs_admin = True
    cats.append(cat_temp)

    browser_locations = []
    for key in ("edge", "chrome", "brave", "vivaldi"):
        base = os.path.expandvars(d[key])
        browser_locations.extend(browser_cache_folders(base))
    # Opera / Opera GX (structure: profile/Cache)
    for key in ("opera", "opera_gx"):
        base = os.path.expandvars(d[key])
        if os.path.isdir(base):
            browser_locations.append(os.path.join(base, "Cache"))
            browser_locations.append(os.path.join(base, "GPUCache"))
    for profile in glob_like(os.path.expandvars(os.path.join(d["firefox"], "*"))):
        browser_locations.append(os.path.join(profile, "cache2"))
    cat_browser = CleanCategory(
        "browser", t("cat.browser.label"), t("cat.browser.desc"),
        browser_locations, "\U0001F310")
    cats.append(cat_browser)

    cat_bin = CleanCategory(
        "recycle", t("cat.recycle.label"), t("cat.recycle.desc"),
        [], "\U0001F5DE")
    cat_bin.recycle_bin = True
    cats.append(cat_bin)

    cat_apps = CleanCategory(
        "apps", t("cat.apps.label"), t("cat.apps.desc"),
        [d["explorer_cache"], d["dump"], d["update_cache"], d["cbs_logs"]],
        "\U00002699")
    cat_apps.needs_admin = True
    cats.append(cat_apps)

    cat_hist = CleanCategory(
        "history", t("cat.history.label"), t("cat.history.desc"),
        [d["recent"]], "\U0001F551")
    cats.append(cat_hist)

    rules = (parse_winapp_rules(default_winapp_file())
             if os.path.exists(default_winapp_file()) else [])
    cat_winapp = CleanCategory(
        "winapp", t("cat.winapp.label"),
        (t("cat.winapp.desc_detected", n=len(rules)) if rules
         else t("cat.winapp.desc_none")),
        [], "\U0001F4E6")
    cat_winapp.rules = [r2 for s in rules for r2 in s.rules]
    cat_winapp.needs_admin = True
    cats.append(cat_winapp)

    return cats
