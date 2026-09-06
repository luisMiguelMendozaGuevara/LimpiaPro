"""LimpiaPro application controller: the seam between the UI and the core.

The UI never talks to categories/utils/winapp2 directly. It consumes a
small API and reacts to Qt signals:

    controller.analyze()                 -> analysis_* signals
    controller.preview(keys)             -> preview_* signals
    controller.clean(keys)               -> clean_* signals
    controller.cancel()                  -> cooperative cancellation
    controller.get_results()             -> list[CategoryResult]
    controller.load_winapp_rules(path)   -> winapp_* signals

All heavy work (scanning, winapp2 parsing, deletion) runs on dedicated
QThread workers; the controller only marshals progress and results. The
UI receives the required event vocabulary: started / progress / result /
finished / error / cancelled.

Safety is enforced by the core (SafetyGuard gates _delete_measured,
_delete_path and REMOVESELF before any filesystem access), never by the
UI or this controller: the UI can request a clean, but it never decides
which paths are safe to delete.

The worker classes also expose plain run() methods so the orchestration
can be exercised synchronously in tests without a QApplication."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QThread, Signal

from . import APP_VERSION
from .categories import build_categories
from .paths import get_cache_file
from .recycle import empty_recycle_bin, recycle_bin_size
from .services import CacheService
from .utils import _errlog
from .winapp2 import invalidate_detect_cache, parse_winapp_rules

# ---------------------------------------------------------------------------
# Module constants / small helpers
# ---------------------------------------------------------------------------

# Cache payload tag: single source of truth (was hardcoded "win32" at the
# AnalysisWorker call site, Lote D3).
PLATFORM_NAME = "win32"


def _cache_payload(categories: Iterable) -> dict[str, dict[str, int]]:
    """Build the {key: {size, files}} snapshot persisted to the scan cache."""
    return {c.key: {"size": c.size, "files": c.files} for c in categories}


# ---------------------------------------------------------------------------
# Typed result models (simple data, no logic).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CategoryResult:
    """One cleaning category as the UI sees it (immutable snapshot)."""

    key: str
    label: str
    description: str
    icon: str
    size: int
    files: int
    needs_admin: bool
    recycle_bin: bool


@dataclass(frozen=True)
class CleanSummary:
    """Aggregate outcome of one clean() operation."""

    removed: int
    errors: int
    freed: int
    cancelled: bool = False


# ---------------------------------------------------------------------------
# Workers (QObject + run(); the controller moves them to QThreads).
# ---------------------------------------------------------------------------


class AnalysisWorker(QObject):
    """Scan every category once, caching the results at the end.

    Progress is per-category (label, fraction): the fraction is estimated
    against the previous run's file count (or 1 when unknown), matching
    the legacy coordinator's behavior. All disk work happens here, on the
    worker thread."""

    progress = Signal(str, float)   # (category label, fraction 0..1)
    category_done = Signal(str)     # category key finished
    finished = Signal()
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, categories: Iterable, should_cancel: Callable[[], bool],
                 cache_service=None, platform_name: str = "",
                 parent: QObject | None = None):
        super().__init__(parent)
        self._categories = list(categories)
        self._should_cancel = should_cancel
        self._cache_service = cache_service
        self._platform_name = platform_name

    def run(self) -> None:
        try:
            for cat in self._categories:
                if self._should_cancel():
                    self.cancelled.emit()
                    return
                estimate = max(cat.files, 1)
                if cat.recycle_bin:
                    cat.size = recycle_bin_size()
                    cat.files = 0
                else:
                    def on_progress(n, cat=cat, estimate=estimate):
                        self.progress.emit(cat.label, min(n / estimate, 1.0))
                    cat.scan(on_progress=on_progress,
                             should_cancel=self._should_cancel)
                self.category_done.emit(cat.key)
            if self._cache_service is not None:
                self._cache_service.save(
                    _cache_payload(self._categories), self._platform_name)
            self.finished.emit()
        except Exception as e:  # never let a worker die silently
            self.failed.emit(str(e))


class PreviewWorker(QObject):
    """Collect per-category preview file lists off the UI thread.

    list_files() also SNAPSHOTS the exact target set, so the subsequent
    clean() deletes exactly what the user saw, without re-walking the
    filesystem (P0-3 / Fase 6)."""

    done = Signal(object)   # list[(key, [paths], scanned)]
    failed = Signal(str)

    def __init__(self, categories: Iterable, limit: int = 1000,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._categories = list(categories)
        self._limit = limit

    def run(self) -> None:
        try:
            out = []
            for cat in self._categories:
                files, scanned = cat.list_files(self._limit)
                out.append((cat.key, files, scanned))
            self.done.emit(out)
        except Exception as e:
            self.failed.emit(str(e))


class CleanWorker(QObject):
    """Delete the selected categories sequentially (each category deletes
    its own targets in parallel internally).

    Progress is cumulative across categories, scaled by each category's
    share of the pre-clean total. Results are not re-scanned afterwards:
    CleanCategory.clean() already updated the category sizes with the
    freed bytes, so get_results() is accurate without a new analysis
    (Fase 6/7).

    When to_recycle is True every target is moved to the recycle bin
    instead of being deleted permanently (user opt-in from settings)."""

    progress = Signal(float)
    log = Signal(str)
    finished = Signal(object)   # CleanSummary
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, categories: Iterable, should_cancel: Callable[[], bool],
                 to_recycle: bool = False,
                 parent: QObject | None = None):
        super().__init__(parent)
        self._categories = list(categories)
        self._should_cancel = should_cancel
        self._to_recycle = to_recycle

    def run(self) -> None:
        # Lote D2: the clean is the most destructive operation; an
        # unexpected exception must still release the UI (failed is wired
        # to operation_error/_release_busy and terminates the thread),
        # never leave it stuck on "busy" forever.
        try:
            self._run_cleaning()
        except Exception as e:  # never let a worker die silently
            self.failed.emit(str(e))

    def _run_cleaning(self) -> None:
        selected = self._categories
        target_all = sum(c.size for c in selected)
        cumulative = 0
        removed = errors = freed = 0
        for cat in selected:
            if self._should_cancel():
                self.cancelled.emit()
                return
            self.log.emit(f"cleaning:{cat.label}")
            if cat.recycle_bin:
                bin_size = recycle_bin_size()
                ok, msg = empty_recycle_bin()
                if ok:
                    freed += bin_size
                cumulative += cat.size
                # Carry the failure message through (the UI translates the
                # ok line; a failure reason may contain ':' so the UI must
                # split with maxsplit).
                self.log.emit(f"recycle:{cat.label}:{'ok' if ok else msg}")
                continue
            # The results step already snapshotted the targets; if not
            # (direct clean), collect the snapshot now so deletion uses
            # exactly the collected set without a second traversal.
            if cat._snapshot is None:
                cat.list_files()
            r, e, f = cat.clean(
                target_bytes=cat.size,
                to_recycle=self._to_recycle,
                on_progress=(lambda frac, cum=cumulative, tot=target_all:
                             self.progress.emit(
                                 cum / tot + frac * (tot - cum) / tot)
                             if tot > 0 else None),
                should_cancel=self._should_cancel)
            cumulative += cat.size
            removed += r
            errors += e
            freed += f
            self.log.emit(f"cleaned:{cat.label}:{r}:{e}:{f}")
        self.finished.emit(CleanSummary(removed=removed, errors=errors,
                                        freed=freed, cancelled=False))


class TaskWorker(QObject):
    """Run a plain callable on a QThread (winapp2 parse, ...)."""

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable[[], object],
                 parent: QObject | None = None):
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception as e:
            self.failed.emit(str(e))


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class LimpiaProController(QObject):
    """Application API: owns categories/cache, drives the workers and
    exposes the event vocabulary the UI subscribes to."""

    # analysis events
    analysis_started = Signal()
    analysis_progress = Signal(str, float)
    category_updated = Signal(str)
    analysis_finished = Signal()
    analysis_cancelled = Signal()

    # preview events
    preview_started = Signal()
    preview_done = Signal(object)
    preview_error = Signal(str)

    # clean events
    clean_started = Signal()
    clean_progress = Signal(float)
    clean_log = Signal(str)
    clean_finished = Signal(object)
    clean_cancelled = Signal()

    # winapp2 events
    winapp_loaded = Signal(object)
    winapp_error = Signal(str)

    # generic
    operation_error = Signal(str)
    busy_changed = Signal(bool)

    def __init__(self, categories=None, cache_service=None,
                 parent: QObject | None = None,
                 defer_winapp: bool = False):
        """Initialize the controller.

        Args:
            categories: Optional category list (tests inject tiny ones).
            cache_service: Optional cache service override.
            parent: Optional Qt parent.
            defer_winapp: Build the winapp category WITHOUT parsing the
                bundled ini (the UI defers that heavy parse to a worker
                after the first paint via load_winapp_rules, E2.1).
        """
        super().__init__(parent)
        self.categories = list(categories) if categories is not None \
            else build_categories(load_winapp=not defer_winapp)
        self.cache_service = cache_service or CacheService(
            get_cache_file(), 1, APP_VERSION)
        self._cancel_requested = False
        self._busy = False
        self._thread: QThread | None = None
        self._worker: QObject | None = None  # keep a ref: GC would kill the signal source

    # ------------------------------------------------------------ state

    @property
    def busy(self) -> bool:
        return self._busy

    def _set_busy(self, value: bool) -> None:
        if value != self._busy:
            self._busy = value
            self.busy_changed.emit(value)

    def _should_cancel(self) -> bool:
        return self._cancel_requested

    # ------------------------------------------------------------- API

    def analyze(self) -> None:
        """Run a full analysis on a worker thread (no-op while busy)."""
        if self._busy:
            return
        self._cancel_requested = False
        self._set_busy(True)
        self.analysis_started.emit()
        worker = AnalysisWorker(
            self.categories, self._should_cancel,
            cache_service=self.cache_service, platform_name=PLATFORM_NAME)
        worker.progress.connect(self.analysis_progress)
        worker.category_done.connect(self.category_updated)
        worker.finished.connect(self.analysis_finished)
        worker.finished.connect(self._release_busy)
        worker.cancelled.connect(self.analysis_cancelled)
        worker.cancelled.connect(self._release_busy)
        worker.failed.connect(self.operation_error)
        worker.failed.connect(self._release_busy)
        self._start_worker(worker, worker.finished, worker.cancelled,
                           worker.failed)

    def preview(self, keys: Iterable[str], limit: int = 1000) -> None:
        """Collect the preview file lists for `keys` on a worker thread."""
        if self._busy:
            return
        self._set_busy(True)
        self.preview_started.emit()
        selected = [c for c in self.categories if c.key in set(keys)]
        worker = PreviewWorker(selected, limit=limit)
        worker.done.connect(self.preview_done)
        worker.done.connect(self._release_busy)
        worker.failed.connect(self.preview_error)
        worker.failed.connect(self._release_busy)
        self._start_worker(worker, worker.done, worker.failed)

    def clean(self, keys: Iterable[str],
              to_recycle: bool = False) -> None:
        """Delete the selected categories on a worker thread.

        Every path still passes through SafetyGuard inside the core right
        before deletion; this controller never decides safety.

        Args:
            keys: The category keys to clean.
            to_recycle: Move targets to the recycle bin instead of
                        deleting them (user opt-in from settings).
        """
        if self._busy:
            return
        selected = [c for c in self.categories if c.key in set(keys)]
        if not selected:
            self.operation_error.emit("no categories selected")
            return
        self._cancel_requested = False
        self._set_busy(True)
        self.clean_started.emit()
        worker = CleanWorker(selected, self._should_cancel,
                             to_recycle=to_recycle)
        worker.progress.connect(self.clean_progress)
        worker.log.connect(self.clean_log)
        # Save the cache FIRST: CleanCategory.clean() already updated the
        # in-memory sizes with the freed bytes, so persisting them keeps
        # the next startup's incremental analysis consistent (Lote D3).
        worker.finished.connect(self._save_results_cache)
        worker.finished.connect(self.clean_finished)
        worker.finished.connect(self._release_busy)
        worker.cancelled.connect(self.clean_cancelled)
        worker.cancelled.connect(self._release_busy)
        # Lote D2: a crashed clean must surface the error and release the
        # busy state (same contract as the other workers).
        worker.failed.connect(self.operation_error)
        worker.failed.connect(self._release_busy)
        self._start_worker(worker, worker.finished, worker.cancelled,
                           worker.failed)

    def cancel(self) -> None:
        """Ask the running operation to stop as soon as possible
        (cooperative: the workers check the flag between chunks)."""
        self._cancel_requested = True

    def get_results(self) -> list[CategoryResult]:
        """Immutable snapshot of the current category results."""
        return [
            CategoryResult(
                key=c.key, label=c.label, description=c.description,
                icon=c.icon, size=c.size, files=c.files,
                needs_admin=c.needs_admin, recycle_bin=c.recycle_bin)
            for c in self.categories
        ]

    def load_winapp_rules(self, path: str) -> None:
        """Parse + detect a winapp2.ini on a worker thread and replace the
        winapp category rules on completion."""
        if self._busy:
            return
        self._set_busy(True)

        def work() -> int:
            # A different ini may carry different Detect= conditions: the
            # memoized results from the previous file must not leak in.
            invalidate_detect_cache()
            rules = parse_winapp_rules(path)
            for cat in self.categories:
                if cat.key == "winapp":
                    cat.rules = [r2 for s in rules for r2 in s.rules]
                    cat.description = (
                        f"detected {len(rules)} apps" if rules
                        else "no rules detected")
                    break
            return len(rules)

        worker = TaskWorker(work)
        worker.done.connect(self.winapp_loaded)
        worker.done.connect(self._release_busy)
        worker.failed.connect(self.winapp_error)
        worker.failed.connect(self._release_busy)
        self._start_worker(worker, worker.done, worker.failed)

    # ---------------------------------------------------------- internals

    def _release_busy(self, *args) -> None:
        self._cancel_requested = False
        self._set_busy(False)

    def _save_results_cache(self, *_args) -> None:
        """Persist current sizes/files into the scan cache (Lote D3).

        CleanCategory.clean() updates each category's size with the freed
        bytes, so saving right after a clean replaces the stale pre-clean
        snapshot AnalysisWorker wrote: the next startup must not present
        pre-clean sizes as "cached" results. save() is best-effort by
        design; anything non-OSError that still escapes only logs."""
        try:
            self.cache_service.save(_cache_payload(self.categories),
                                    PLATFORM_NAME)
        except Exception as e:
            _errlog(f"post-clean cache save failed: {e!r}")

    def _start_worker(self, worker: QObject,
                      *terminal: object) -> None:
        """Move `worker` to a fresh QThread and run it.

        Any of the terminal signals quits the thread; cleanup happens on
        thread.finished. The thread is intentionally NOT parented to the
        controller: a parent would destroy it when the controller is
        garbage-collected while deleteLater is already queued, which
        double-deletes the QThread and aborts the process. The Python
        references (self._thread / self._worker) keep both objects alive
        until the thread finishes."""
        thread = QThread()
        self._thread = thread
        self._worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        for sig in terminal:
            sig.connect(thread.quit)

        def _drop_worker():
            # Only drop the references when this thread owns them: the
            # previous thread's finished may fire after a newer worker
            # was already started, and clearing them would let GC kill
            # the new worker's signal source mid-flight.
            if self._worker is worker:
                self._worker = None
            if self._thread is thread:
                self._thread = None

        thread.finished.connect(_drop_worker)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread = thread
        thread.start()
