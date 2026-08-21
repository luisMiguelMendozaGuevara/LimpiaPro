"""Cleaning categories: system locations and winapp2 rules.

Each CleanCategory owns a list of locations (paths with %ENV% templates and
optional glob wildcards) or a set of parsed winapp2 rules. One single
traversal (_iter_targets) feeds scanning, preview listing and deletion, so
the same matching logic (masks, RECURSE, ExcludeKey) applies to all three.

Category labels and descriptions shown in the UI are translated through
i18n.t() keys ("cat.*")."""

import os
import threading

from .audit_log import audit
from .i18n import t
from .utils import (
    PROGRESS_DELETE,
    PROGRESS_RULES,
    DeleteError,
    _delete_measured,
    _fast_folder_stats,
    _iter_tree_files,
    _parallel_map,
    glob_like,
    is_safe_delete_target,
)
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
        self.rules: list = []
        self.size = 0
        self.files = 0
        self.errors = 0
        self.delete_errors = []
        self._snapshot = None

    def _locations_existing(self):
        """Expand %ENV% vars and glob wildcards, keeping existing paths only."""
        out = []
        for loc in self.locations:
            for h in glob_like(os.path.expandvars(loc)):
                if os.path.exists(h):
                    out.append(h)
        return out

    @staticmethod
    def _match_re(name: str, patterns_re) -> bool:
        """Case-insensitive filename match against precompiled regexes
        (fnmatch.translate). Empty pattern lists match everything."""
        if not patterns_re:
            return True
        for rx in patterns_re:
            if rx.match(name):
                return True
        return False

    def _rule_roots(self):
        """Yield (rule, existing_root) for each winapp2 rule.

        The root is normalized and absolutized exactly once here:
        is_excluded() (winapp2) then receives absolute paths and only needs
        normcase, avoiding one GetFullPathName syscall per file. Roots that
        are themselves junctions are skipped: walking one would traverse
        the junction target (os.walk descends into junctions) and generate
        targets that live outside the rule's physical tree."""
        for rule in self.rules or []:
            root = os.path.normcase(os.path.abspath(
                os.path.expandvars(rule.root)))
            if os.path.exists(root) and not os.path.isjunction(root):
                yield rule, root

    def _iter_targets(self, should_cancel=None):
        """Iterate (rule_or_None, path) over everything the category would
        clean.

        One single traversal for scan, preview and deletion. Winapp2 rules
        apply masks, recursion and ExcludeKey exclusions; plain categories
        only touch the top level of each location (folders get removed
        whole when cleaning)."""
        if self.rules:
            for rule, root in self._rule_roots():
                if should_cancel and should_cancel():
                    return
                if os.path.isfile(root):
                    if (self._match_re(os.path.basename(root),
                                       rule.patterns_re)
                            and not rule.is_excluded(root)):
                        yield rule, root
                    continue
                # One scandir traversal per root (never into junctions);
                # DirEntry carries the stat, so the scan can reuse it.
                for entry in _iter_tree_files(root, should_cancel,
                                              recurse=rule.recurse):
                    if (self._match_re(entry.name, rule.patterns_re)
                            and not rule.is_excluded(entry.path)):
                        yield rule, entry.path
        else:
            for loc in self._locations_existing():
                if should_cancel and should_cancel():
                    return
                if os.path.isdir(loc):
                    try:
                        for name in os.listdir(loc):
                            if should_cancel and should_cancel():
                                return
                            yield None, os.path.join(loc, name)
                    except OSError:
                        pass
                else:
                    yield None, loc

    def _scan_rules(self, on_progress=None, should_cancel=None):
        """Scan winapp2-rule targets: measure each matched file/folder.

        Each category is scanned on its own thread; roots are walked
        serially inside it (extra parallelism gains nothing on a regular
        disk). File sizes come from the DirEntry stat of the shared
        traversal, so no extra stat syscall is paid per file."""
        self.size = 0
        self.files = 0
        for rule, root in self._rule_roots():
            if should_cancel and should_cancel():
                break
            if os.path.isfile(root):
                if (self._match_re(os.path.basename(root),
                                   rule.patterns_re)
                        and not rule.is_excluded(root)):
                    try:
                        self.size += os.path.getsize(root)
                    except OSError:
                        pass
                    self.files += 1
                continue
            for entry in _iter_tree_files(root, should_cancel,
                                          recurse=rule.recurse):
                if (self._match_re(entry.name, rule.patterns_re)
                        and not rule.is_excluded(entry.path)):
                    try:
                        self.size += entry.stat().st_size
                    except OSError:
                        pass
                    self.files += 1
                    if on_progress and self.files % PROGRESS_RULES == 0:
                        on_progress(self.files)
        return self.size

    def scan(self, on_progress=None, should_cancel=None):
        """Measure the category: total bytes and file count. Rule-based
        categories use _scan_rules; plain ones use the fast scandir stats."""
        audit.log_operation(
            operation="scan",
            category=self.key,
            action="start",
            result="success"
        )
        
        if self.rules:
            size = self._scan_rules(on_progress, should_cancel)
        else:
            self.size = 0
            self.files = 0
            for loc in self._locations_existing():
                if should_cancel and should_cancel():
                    break
                if os.path.isdir(loc):
                    size, files = _fast_folder_stats(loc, on_progress, should_cancel)
                    self.size += size
                    self.files += files
                else:
                    self.files += 1
                    try:
                        self.size += os.path.getsize(loc)
                    except OSError:
                        pass
            size = self.size
        
        audit.log_operation(
            operation="scan",
            category=self.key,
            action="complete",
            result="success",
            details={"size_bytes": self.size, "file_count": self.files}
        )
        return size

    def list_files(self, limit=1000):
        """Return (paths, scanned_count) for the preview dialog and SNAPSHOT
        the exact target set (P0-3).

        The preview shows the first `limit` paths, but the snapshot keeps
        the full list so clean() deletes exactly what was collected here
        (revalidated per-path by the safety layer), instead of re-walking
        the filesystem and picking up new files created in between."""
        targets = list(self._iter_targets())
        self._snapshot = targets
        scanned = len(targets)
        files = [path for _rule, path in targets[:limit]]
        return files, scanned

    def _collect(self):
        """Return (targets, remove_roots) to delete. Prefers the snapshot
        taken by list_files (clean = what the preview showed); falls back
        to a fresh walk when no preview happened."""
        if self._snapshot is not None:
            targets = [p for _r, p in self._snapshot]
            remove_roots = [os.path.abspath(os.path.expandvars(r.root))
                            for r, _p in self._snapshot
                            if r is not None and r.remove_self]
            self._snapshot = None
        else:
            targets = []
            remove_roots = []
            for rule, path in self._iter_targets():
                targets.append(path)
                if rule is not None and rule.remove_self:
                    root = os.path.abspath(os.path.expandvars(rule.root))
                    if root not in remove_roots:
                        remove_roots.append(root)
        targets = list(dict.fromkeys(targets))
        return targets, list(dict.fromkeys(remove_roots))

    def clean(self, on_file=None, on_progress=None, target_bytes=0,
              should_cancel=None):
        """Delete every target of the category in parallel.

        Targets are collected in one pass and deleted through _parallel_map
        (plain categories only remove the top level of each location;
        folders are deleted whole with rmtree). Returns (removed, errors,
        freed_bytes).

        After cleaning there is no re-scan here: the UI re-analyzes
        everything when the cleanup finishes (analyze_all). Approximating
        until that refresh avoids one extra full traversal."""
        targets, remove_roots = self._collect()
        if on_file:
            for target in targets:
                on_file(target)

        lock = threading.Lock()
        state = {"removed": 0, "errors": 0, "freed": 0, "done": 0}
        error_detail: list[DeleteError] = []

        def _delete_one(target):
            if should_cancel and should_cancel():
                return
            ok, size, errors = _delete_measured(target)
            
            # Audit log: record each deletion attempt (P1-16)
            if ok:
                audit.log_operation(
                    operation="cleanup",
                    category=self.key,
                    action="delete",
                    path=target,
                    result="success",
                    details={"freed_bytes": size}
                )
            else:
                # Log each error with its details
                for err in errors:
                    audit.log_operation(
                        operation="cleanup",
                        category=self.key,
                        action="delete",
                        path=err.path,
                        result="failed",
                        error_code=err.code,
                        error_msg=err.message,
                        details={"operation": err.operation, "kind": err.kind}
                    )
            
            with lock:
                state["done"] += 1
                if ok:
                    state["removed"] += 1
                    state["freed"] += size
                else:
                    state["errors"] += 1
                error_detail.extend(errors)
                done, freed = state["done"], state["freed"]
            # Chunked progress so the GUI is not flooded with after(0, ...).
            if on_progress and target_bytes > 0 and done % PROGRESS_DELETE == 0:
                on_progress(min(freed / target_bytes, 1.0))

        _parallel_map(_delete_one, targets)

        # REMOVESELF: remove the rule folder itself when left empty. The
        # safety layer still applies: a rule must not remove a protected
        # root even if it asks for REMOVESELF.
        for root in remove_roots:
            if not is_safe_delete_target(root):
                error_detail.append(DeleteError(
                    path=root, operation="rmdir", kind="safety",
                    message="REMOVESELF refused by delete safety policy"))
                state["errors"] += 1
                continue
            try:
                os.rmdir(root)
            except OSError:
                state["errors"] += 1

        removed = state["removed"]
        errors = state["errors"]
        freed = state["freed"]
        self.size = max(0, self.size - freed)
        self.files = removed
        self.errors = errors
        self.delete_errors = error_detail
        return removed, errors, freed

    def error_summary(self) -> dict[str, int]:
        """Count deleted-path failures per kind (for the UI/log report)."""
        out: dict[str, int] = {}
        for e in getattr(self, "delete_errors", []):
            out[e.kind] = out.get(e.kind, 0) + 1
        return out


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
