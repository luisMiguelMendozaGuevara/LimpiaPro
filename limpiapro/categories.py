"""Cleaning categories: system locations and winapp2 rules.

Each CleanCategory owns a list of locations (paths with %ENV% templates and
optional glob wildcards) or a set of parsed winapp2 rules. One single
traversal (_iter_targets) feeds scanning, preview listing and deletion, so
the same matching logic (masks, RECURSE, ExcludeKey) applies to all three.

Category labels and descriptions shown in the UI are translated through
i18n.t() keys ("cat.*").

Architecture Overview:
    - CleanCategory is the atomic unit of work. It encapsulates:
      * What to clean (locations or winapp2 rules)
      * How to measure it (scan)
      * What files are involved (list_files with snapshot)
      * How to delete it (clean with parallel execution)
    - build_categories() constructs the default set with i18n translations.
    - Snapshot integrity (P0-3): list_files() captures an immutable snapshot
      of targets, ensuring clean() deletes exactly what the preview showed.
"""

import contextlib
import os
import threading

from .audit_log import audit
from .i18n import t
from .utils import (
    PROGRESS_DELETE,
    DeleteError,
    _delete_measured,
    _fast_folder_stats,
    _iter_tree_files,
    _parallel_map,
    glob_like,
    is_junction,
    is_safe_delete_target,
)
from .winapp2 import default_winapp_file, parse_winapp_rules


def user_dirs():
    """Return a dictionary of common user/system directories as %ENV% templates.
    
    These templates are expanded at runtime via os.path.expandvars(), ensuring
    they work correctly regardless of the user profile or system configuration.
    
    Returns:
        dict[str, str]: Mapping of category keys to environment-variable-templated paths.
        
    Example:
        >>> dirs = user_dirs()
        >>> dirs["temp"]
        '%TEMP%'
        >>> os.path.expandvars(dirs["temp"])
        'C:\\\\Users\\\\john\\\\AppData\\\\Local\\\\Temp'
    """
    return {
        "temp": r"%TEMP%",
        # %SystemRoot% instead of a hardcoded C:\Windows: Windows can live
        # on another drive (or be relocated), and the docstring contract is
        # that every entry is an expandable template.
        "win_temp": r"%SystemRoot%\Temp",
        "prefetch": r"%SystemRoot%\Prefetch",
        "recent": r"%APPDATA%\Microsoft\Windows\Recent",
        "explorer_cache": r"%LOCALAPPDATA%\Microsoft\Windows\Explorer",
        "edge": r"%LOCALAPPDATA%\Microsoft\Edge\User Data",
        "chrome": r"%LOCALAPPDATA%\Google\Chrome\User Data",
        "brave": r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data",
        "vivaldi": r"%LOCALAPPDATA%\Vivaldi\User Data",
        "opera": r"%APPDATA%\Opera Software\Opera Stable",
        "opera_gx": r"%APPDATA%\Opera Software\Opera GX Stable",
        "firefox": r"%APPDATA%\Mozilla\Firefox\Profiles",
        "update_cache": r"%SystemRoot%\SoftwareDistribution\Download",
        "cbs_logs": r"%SystemRoot%\Logs\CBS",
        "dump": r"%LOCALAPPDATA%\CrashDumps",
    }


def browser_cache_folders(base):
    """Generate cache folder candidates for Chromium-based browsers.
    
    For each profile directory under the browser's User Data folder, this
    function yields a list of cache-related subdirectories. Profiles that
    never created these folders simply don't have them, so listing all
    candidates is cheap and safe (non-existent paths are filtered later).
    
    Args:
        base (str): Path to the browser's User Data directory (e.g.,
                    '%LOCALAPPDATA%\\Google\\Chrome\\User Data').
                    
    Returns:
        list[str]: List of absolute paths to cache folders across all profiles.
        
    Notes:
        - Cache folders include: Cache, Code Cache, GPUCache, Service Worker caches,
          ShaderCache, DawnCache, blob_storage, and CachedData.
        - The function silently ignores profiles that don't exist or can't be read.
    """
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
            result.extend(os.path.join(p, cf) for cf in cache_folders)
    except OSError:
        pass
    return result


class CleanCategory:
    """One cleaning category with its source locations or winapp2 rules.
    
    This is the central abstraction for all cleanup operations. It encapsulates:
    - **What to clean**: Either a list of filesystem locations (paths with %ENV%
      templates and wildcards) or a set of winapp2 rules (FileKey directives).
    - **How to measure**: scan() calculates total size and file count.
    - **What's involved**: list_files() generates a preview and creates an
      immutable snapshot of targets.
    - **How to delete**: clean() removes all targets in parallel, respecting
      the snapshot to prevent race conditions.
    
    Special Cases:
        - `recycle_bin` categories are handled by the shell API (empty_recycle_bin),
          not standard file deletion.
        - Winapp2 rules support masks, recursion (RECURSE), and exclusions
          (ExcludeKey), which are applied during scanning and deletion.
    
    Thread Safety:
        - scan(), list_files(), and clean() are designed to run on background
          threads (QThread workers in the controller).
        - The _snapshot attribute ensures clean() deletes exactly what was
          collected by list_files(), preventing race conditions where new
          files created between preview and deletion are accidentally removed.
    """

    def __init__(self, key, label, description, locations, icon="\U0001F5D1"):
        """Initialize a CleanCategory instance.
        
        Args:
            key (str): Unique identifier for the category (e.g., "temp", "browser").
            label (str): Human-readable name for display in the UI.
            description (str): Detailed explanation of what the category cleans.
            locations (list[str]): List of filesystem paths (with %ENV% templates
                                   and optional wildcards) or an empty list if
                                   the category uses winapp2 rules.
            icon (str, optional): Unicode emoji or icon identifier for the UI.
                                  Defaults to trash can emoji.
        """
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
        # SNAPSHOT INTEGRITY (P0-3): This holds the immutable list of targets
        # collected by list_files(). clean() uses this snapshot to ensure it
        # deletes exactly what the preview showed, preventing race conditions
        # where new files created between preview and deletion are removed.
        self._snapshot = None

    def _locations_existing(self):
        """Expand %ENV% variables and glob wildcards, returning only existing paths.
        
        This helper ensures that scan/clean operations only process paths that
        actually exist on the filesystem, avoiding errors from non-existent
        directories or files.
        
        Returns:
            list[str]: List of absolute paths that exist after expansion.
        """
        out = []
        for loc in self.locations:
            out.extend(h for h in glob_like(os.path.expandvars(loc))
                       if os.path.exists(h))
        return out

    @staticmethod
    def _match_re(name: str, patterns_re) -> bool:
        """Case-insensitive filename match against precompiled regexes.
        
        Args:
            name (str): Filename to match (e.g., "cache.tmp").
            patterns_re (tuple[re.Pattern]): Precompiled regex patterns from
                                             fnmatch.translate(). Empty tuple
                                             matches everything (wildcard "*").
                                             
        Returns:
            bool: True if the filename matches any pattern, or if patterns_re is empty.
            
        Notes:
            - Empty pattern lists match everything (equivalent to wildcard "*").
            - Patterns are precompiled for performance (avoiding repeated fnmatch calls).
        """
        if not patterns_re:
            return True
        return any(rx.match(name) for rx in patterns_re)

    def _rule_roots(self):
        """Yield (rule, existing_root) pairs for each winapp2 rule.
        
        This generator normalizes and absolutizes the root path exactly once,
        optimizing performance by avoiding repeated GetFullPathName syscalls.
        Junctions (reparse points) are skipped to prevent traversing into
        their targets, which could lead to counting/deleting files outside
        the rule's physical tree.
        
        Yields:
            tuple[WinAppRule, str]: (rule, normalized_absolute_root) for each
                                    existing, non-junction root.
                                    
        Notes:
            - Junctions are detected with utils.is_junction() and skipped.
            - Roots are normalized with os.path.normcase() and os.path.abspath().
            - Only existing roots are yielded (os.path.exists check).
        """
        for rule in self.rules or []:
            root = os.path.normcase(os.path.abspath(
                os.path.expandvars(rule.root)))
            if os.path.exists(root) and not is_junction(root):
                yield rule, root

    def _iter_root_targets(self, rule, root, should_cancel=None):
        """Yield (path, entry) targets for ONE (rule, root) pair.

        Single source of truth for the winapp2 match/exclude logic (O3):
        _iter_targets (preview/snapshot) and _scan_rules (measurement)
        used to duplicate the mask-match + ExcludeKey check, which let
        them drift apart. `entry` is the DirEntry from the shared
        traversal (so the scan can stat for free) or None when the root
        itself is the target file.

        Args:
            rule (WinAppRule): Rule whose masks/exclusions apply.
            root (str): Normalized, existing, non-junction root path.
            should_cancel (callable, optional): Cooperative cancellation.

        Yields:
            tuple[str, os.DirEntry | None]: (target_path, dir_entry_or_None).
        """
        if os.path.isfile(root):
            if (self._match_re(os.path.basename(root), rule.patterns_re)
                    and not rule.is_excluded(root)):
                yield root, None
            return
        # One scandir traversal per root (never into junctions);
        # DirEntry carries the stat, so the scan can reuse it.
        for entry in _iter_tree_files(root, should_cancel,
                                      recurse=rule.recurse):
            if (self._match_re(entry.name, rule.patterns_re)
                    and not rule.is_excluded(entry.path)):
                yield entry.path, entry

    def _iter_targets(self, should_cancel=None):
        """Iterate over all targets the category would clean.
        
        This is the single source of truth for scanning, preview, and deletion.
        It applies winapp2 masks, recursion flags, and ExcludeKey exclusions
        consistently across all operations. For plain categories (no rules),
        it only touches the top level of each location (folders are removed
        whole during cleaning).
        
        Args:
            should_cancel (callable, optional): Zero-argument function that
                                                returns True to stop iteration.
                                                Used for cooperative cancellation.
                                                
        Yields:
            tuple[WinAppRule | None, str]: (rule_or_None, absolute_path) for
                                           each target. rule_or_None is None
                                           for plain categories.
                                           
        Notes:
            - Cooperative cancellation: Checks should_cancel() between iterations.
            - Winapp2 rules: Applies masks (patterns_re), recursion (RECURSE flag),
              and exclusions (ExcludeKey) via rule.is_excluded().
            - Plain categories: Only top-level items in each location are yielded.
            - Junctions: Never descended into (handled by _iter_tree_files).
        """
        if self.rules:
            for rule, root in self._rule_roots():
                if should_cancel and should_cancel():
                    return
                for path, _entry in self._iter_root_targets(
                        rule, root, should_cancel):
                    yield rule, path
        else:
            for loc in self._locations_existing():
                if should_cancel and should_cancel():
                    return
                # SECURITY: never list THROUGH a reparse point. A symlink or
                # junction sitting under a cleanup location would otherwise
                # expose its TARGET's contents as deletable paths (a link in
                # %TEMP% pointing at Documents would delete the documents).
                # The link itself is yielded so it is removed as a link.
                if (os.path.isdir(loc) and not is_junction(loc)
                        and not os.path.islink(loc)):
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

        Categories are scanned one at a time by the controller worker;
        the ROOTS inside each category are walked in parallel through
        _parallel_map (Lote D7) — multi-root categories (browser caches,
        winapp2 FileKeys) overlap their directory traversal, and the
        per-root results are summed deterministically in rule order.
        File sizes come from the DirEntry stat of the shared traversal,
        so no extra stat syscall is paid per file.

        Args:
            on_progress (callable, optional): Function called with the
                                              running file count after each
                                              root completes.
            should_cancel (callable, optional): Zero-argument function that
                                                returns True to stop scanning.
                                                Checked by every root worker
                                                and between entries.

        Returns:
            int: Total size in bytes of all matched targets.

        Notes:
            - Parallel roots (D7): each (rule, root) pair is scanned in a
              pool worker; workers never touch shared state, they return
              (size, files) pairs that the caller accumulates.
            - Cancellation: workers return partial counts early; results
              from cancelled workers are still summed (caller discards).
            - Error handling: a crashed worker yields None from
              _parallel_map and contributes nothing; OSError on individual
              files is silently ignored inside the worker.
        """
        pairs = list(self._rule_roots())

        def _scan_one_root(pair):
            rule, root = pair
            root_size = 0
            root_files = 0
            for path, entry in self._iter_root_targets(rule, root,
                                                       should_cancel):
                if entry is not None:
                    with contextlib.suppress(OSError):
                        root_size += entry.stat().st_size
                else:
                    with contextlib.suppress(OSError):
                        root_size += os.path.getsize(path)
                root_files += 1
            return root_size, root_files

        results = _parallel_map(_scan_one_root, pairs)
        # O1-lite: accumulate LOCALLY and commit once. The worker thread
        # used to mutate self.size/self.files after every root while the
        # UI thread read them concurrently; now the UI only ever sees the
        # pre-scan values or the final consistent ones.
        total_size = 0
        total_files = 0
        for res in results:
            if res is None:  # crashed worker: contributes nothing
                continue
            size_part, files_part = res
            total_size += size_part
            total_files += files_part
            if on_progress:
                on_progress(total_files)
        self.size = total_size
        self.files = total_files
        return self.size

    def scan(self, on_progress=None, should_cancel=None):
        """Measure the category: total bytes and file count.
        
        This is the primary method for analyzing how much space can be freed.
        Rule-based categories use _scan_rules (winapp2 logic); plain categories
        use _fast_folder_stats (optimized scandir traversal).
        
        Args:
            on_progress (callable, optional): Function called with file count
                                              periodically during scanning.
            should_cancel (callable, optional): Zero-argument function that
                                                returns True to stop scanning.
                                                
        Returns:
            int: Total size in bytes of all targets in the category.
            
        Notes:
            - Audit logging: Logs operation start and completion with results.
            - Cooperative cancellation: Respects should_cancel() between locations.
            - Performance: Uses cached DirEntry stats to avoid redundant syscalls.
        """
        audit.log_operation(
            operation="scan",
            category=self.key,
            action="start",
            result="success"
        )
        
        if self.rules:
            size = self._scan_rules(on_progress, should_cancel)
        else:
            # Lote D7: locations are measured in parallel (per-location
            # workers return (size, files); progress is reported from this
            # thread after each location completes, never from workers).
            locs = self._locations_existing()

            def _scan_one_location(loc):
                if should_cancel and should_cancel():
                    return 0, 0
                # SECURITY: reparse points are never walked (listing through
                # a symlink/junction would measure its target's contents).
                if (os.path.isdir(loc) and not is_junction(loc)
                        and not os.path.islink(loc)):
                    # No on_progress here: callbacks would run on pool
                    # threads; the caller reports progress per location.
                    return _fast_folder_stats(loc, None, should_cancel)
                loc_size = 0
                with contextlib.suppress(OSError):
                    loc_size = os.path.getsize(loc)
                return loc_size, 1

            results = _parallel_map(_scan_one_location, locs)
            total_size = 0
            total_files = 0
            for res in results:
                if res is None:  # crashed worker: contributes nothing
                    continue
                size_part, files_part = res
                total_size += size_part
                total_files += files_part
                if on_progress:
                    on_progress(total_files)
            # O1-lite: single commit instead of per-location mutation.
            self.size = total_size
            self.files = total_files
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
        the filesystem and picking up new files created in between.
        
        Args:
            limit (int, optional): Maximum number of paths to return for preview.
                                   Defaults to 1000 to prevent UI overload.
                                   
        Returns:
            tuple[list[str], int]: (preview_paths, total_scanned_count)
            
        Notes:
            - SNAPSHOT INTEGRITY (P0-3): This method creates an immutable snapshot
              of all targets. clean() uses this snapshot to ensure it deletes
              exactly what the preview showed, preventing race conditions.
            - The snapshot is stored in self._snapshot and consumed by clean().
            - If no preview is requested before clean(), clean() will generate
              a fresh snapshot internally.
        """
        targets = list(self._iter_targets())
        self._snapshot = targets
        scanned = len(targets)
        files = [path for _rule, path in targets[:limit]]
        return files, scanned

    def _collect(self):
        """Return (targets, remove_roots) to delete.
        
        Prefers the snapshot taken by list_files (clean = what the preview
        showed); falls back to a fresh walk when no preview happened. Also
        collects remove_roots for REMOVESELF winapp2 rules.
        
        Returns:
            tuple[list[str], list[str]]: (targets_to_delete, roots_to_remove_if_empty)
            
        Notes:
            - Snapshot preference: Uses self._snapshot if available (from list_files).
            - Fallback: If no snapshot, generates targets via _iter_targets().
            - REMOVESELF: Collects roots of winapp2 rules with REMOVESELF flag.
              These roots are removed after deletion if they're empty.
            - Deduplication: Removes duplicate paths using dict.fromkeys().
        """
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
              should_cancel=None, to_recycle: bool = False):
        """Delete every target of the category in parallel.
        
        Targets are collected in one pass and deleted through _parallel_map
        (plain categories only remove the top level of each location;
        folders are deleted whole with rmtree). Returns (removed, errors,
        freed_bytes).
        
        After cleaning there is no re-scan here: the UI re-analyzes
        everything when the cleanup finishes (analyze_all). Approximating
        until that refresh avoids one extra full traversal.
        
        Args:
            on_file (callable, optional): Function called with each target path
                                          before deletion (for UI logging).
            on_progress (callable, optional): Function called with progress
                                              fraction (0.0 to 1.0) periodically.
            target_bytes (int, optional): Expected total bytes to delete, used
                                          for progress calculation. Defaults to 0.
            should_cancel (callable, optional): Zero-argument function that
                                                returns True to stop deletion.
            to_recycle (bool, optional): Move targets to the recycle bin
                                                instead of deleting them
                                                (recoverable cleanup).
                                                Defaults to False.
                                                
        Returns:
            tuple[int, int, int]: (removed_count, error_count, freed_bytes)
            
        Notes:
            - Parallel deletion: Uses _parallel_map with ThreadPoolExecutor.
            - Progress reporting: Chunked (every PROGRESS_DELETE files) to avoid
              flooding the UI with updates.
            - Audit logging: Records each deletion attempt with success/failure
              details (P1-16). Records are written in batches (Lote D6) and
              the operation closes with a per-category "summary" record.
            - REMOVESELF: After deletion, attempts to remove roots marked with
              REMOVESELF if they're empty. Respects safety layer.
            - Error handling: Collects DeleteError objects for detailed reporting.
        """
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
            ok, size, errors = _delete_measured(target, to_recycle=to_recycle)
            
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

        # Lote D6: per-file audit records are batched (one write every
        # _BATCH_FLUSH_EVERY records instead of one open/append/close per
        # file) and the operation closes with a per-category summary.
        with audit.batched():
            _parallel_map(_delete_one, targets)

            # REMOVESELF: remove the rule folder itself when left empty.
            # The safety layer still applies: a rule must not remove a
            # protected root even if it asks for REMOVESELF.
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
            audit.log_operation(
                operation="cleanup",
                category=self.key,
                action="summary",
                result="success",
                details={"removed": removed, "errors": errors,
                         "freed_bytes": freed,
                         "mode": "recycle" if to_recycle else "delete"})

        self.size = max(0, self.size - freed)
        self.files = removed
        self.errors = errors
        self.delete_errors = error_detail
        return removed, errors, freed

    def error_summary(self) -> dict[str, int]:
        """Count deleted-path failures per kind (for the UI/log report).
        
        Returns:
            dict[str, int]: Mapping of error kind (e.g., "access_denied", "in_use")
                           to count of occurrences.
                           
        Notes:
            - Error kinds are defined in utils._classify_error().
            - Used by the UI to display a breakdown of deletion failures.
        """
        out: dict[str, int] = {}
        for e in getattr(self, "delete_errors", []):
            out[e.kind] = out.get(e.kind, 0) + 1
        return out


def build_categories(load_winapp: bool = True):
    """Build the default category set with translated labels/descriptions.

    Labels are resolved through i18n.t() at build time (the language is
    fixed at import, before any window exists). This function constructs
    the standard set of cleaning categories:

    - temp: Temporary files (TEMP, Windows\\Temp, Prefetch)
    - browser: Browser caches (Edge, Chrome, Brave, Vivaldi, Opera, Firefox)
    - recycle: Recycle Bin (special case, uses shell API)
    - apps: Application caches (Explorer, CrashDumps, Windows Update, CBS logs)
    - history: Recent files history
    - winapp: Winapp2.ini rules (detected applications)

    Args:
        load_winapp: Parse + detect the bundled winapp2.ini at build time
            (the historical behavior, ~0.2-0.5 s on Windows). Pass False to
            create the winapp category EMPTY so the UI can defer the heavy
            parse to a worker thread after the first paint (Lote E2.1);
            `controller.load_winapp_rules()` fills it in later.

    Returns:
        list[CleanCategory]: List of initialized CleanCategory instances.

    Notes:
        - needs_admin flag is set for categories requiring elevated privileges.
        - Browser cache detection: Scans for profile-specific cache folders.
        - Winapp2 integration: Loads and parses winapp2.ini if it exists.
        - i18n: Labels and descriptions are translated via i18n.t() keys.
    """
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
    browser_locations.extend(
        os.path.join(profile, "cache2")
        for profile in glob_like(os.path.expandvars(
            os.path.join(d["firefox"], "*"))))
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

    rules = ((parse_winapp_rules(default_winapp_file())
              if load_winapp else [])
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
