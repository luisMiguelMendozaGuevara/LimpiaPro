"""LimpiaPro main window (PySide6 replica of the legacy CleanerApp).

This module implements the main application window using PySide6. It
replicates the look and feel of the legacy CustomTkinter interface while
providing a modern, native Windows experience.

Architecture:
    - Sidebar navigation with six pages (Limpieza, Inicio, Duplicados,
      Windows Update, Desinstalar, Registro).
    - Lazily built QStackedWidget: pages are instantiated only when the
      user navigates to them, reducing startup time.
    - Host surface: exposes the same API the legacy pages used (busy,
      set_busy, set_status, log, categories, confirm_clean, ...) so that
      pages can be reused with minimal changes.
    - Controller integration: clean-page flows run through the
      LimpiaProController workers; other pages use run_async.

Design Principles:
1. Lazy Loading: Pages are built on-demand to minimize startup overhead.
2. Separation of Concerns: The window manages layout and navigation;
   business logic lives in the controller.
3. Graceful Shutdown: Running operations are cooperatively cancelled
   before the window closes.
"""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..i18n import LANG, set_language, t
from ..settings import Settings
from ..utils import _errlog, format_size, humanize_duration, is_admin
from ..winapp2 import default_winapp_file
from . import constants, icons
from . import theme as ui_theme
from .dialogs import app_info, readonly_toplevel, structured_confirm
from .pages import (
    CleanPage,
    DuplicatePage,
    LogPage,
    SettingsPage,
    StartupPage,
    UninstallPage,
    UpdatePage,
)

if TYPE_CHECKING:  # imported lazily at runtime; annotations only here
    from ..controller import CleanSummary, LimpiaProController


# Navigation configuration: (page_key, i18n_key)
_NAV = [
    ("clean", "nav.clean"),
    ("startup", "nav.startup"),
    ("dupes", "nav.dupes"),
    ("update", "nav.update"),
    ("uninstall", "nav.uninstall"),
    ("log", "nav.log"),
    ("settings", "nav.settings"),
]


class MainWindow(QMainWindow):
    """Application window: sidebar navigation, pages and global state.

    This class serves as the central hub of the PySide6 interface. It
    owns the controller, manages the page stack, and provides the host
    API that pages use to interact with the application state.

    Attributes:
        settings (Settings): The application's user preferences.
        controller (LimpiaProController): The MVC controller instance.
        busy (bool): Global busy flag.
        scanner: Most recent DuplicateScanner (set by duplicates_page; its
                 snapshot feeds duplicate deletion).
        _pages (dict): Cache of instantiated page widgets.
        _closing (bool): Flag to prevent multiple close attempts.
    """

    def __init__(self, settings: Settings | None = None,
                 controller: LimpiaProController | None = None):
        """Initialize the MainWindow.

        Args:
            settings: Optional Settings instance. If None, loads from disk.
            controller: Optional LimpiaProController. If None, creates a new one.
        """
        _t0 = time.perf_counter()
        super().__init__()
        from ..controller import LimpiaProController as _LPC
        self.settings = (settings or Settings.load()).validate()
        # Apply the SAVED language BEFORE any widget is built: every label
        # resolves t() at construction time, so doing it later (or never,
        # which was the case: only the settings page called set_language)
        # left the whole interface in the detected language.
        set_language(self.settings.language)
        _errlog(f"qt: language={LANG} (settings={self.settings.language!r})")
        # E2.1: never parse the bundled winapp2.ini synchronously here —
        # that delayed the first visible frame by the whole detection pass.
        # The rules load on a worker right after the window paints.
        self.controller = controller or _LPC(defer_winapp=True)
        self.busy = False
        self.scanner = None
        self._pages: dict[str, QWidget] = {}
        self._closing = False
        self._auto_analyze_done = False
        # E2.1: the bundled winapp2.ini parses on a worker AFTER the first
        # paint (defer_winapp controller); the auto-analysis only waits for
        # it when the cache is stale and a scan is actually due.
        self._winapp_ready = False
        self._winapp_load_is_startup = True
        self._winapp_retries = 0
        self._auto_analyze_pending = False

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} - {t('app.window_subtitle')}")
        self.resize(1000, 680)
        self.setMinimumSize(860, 560)

        self._build_ui()
        _errlog(f"qt: ui built in {time.perf_counter() - _t0:.3f}s")
        self._wire_controller()
        ui_theme.apply_mica_backdrop(self)
        self.apply_theme()
        self.show_page("clean")
        _errlog(f"qt: window ready in {time.perf_counter() - _t0:.3f}s")

        self.log(t("log.started_admin" if is_admin() else "log.started_no_admin",
                   app=APP_NAME, ver=APP_VERSION))
        # The first analysis starts after the window paints (showEvent),
        # never blocking the first frame.
        _errlog("qt: window created")

    # ------------------------------------------------------------- layout

    def _build_ui(self) -> None:
        """Construct the main UI layout: sidebar + page stack."""
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        root.addWidget(self.sidebar)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _build_sidebar(self) -> QFrame:
        """Construct the navigation sidebar with logo, nav buttons, and theme toggle."""
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(200)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 16, 10, 14)
        lay.setSpacing(4)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(8)
        logo_icon = QLabel()
        # The application (exe) icon, loaded from the bundle (never from a
        # mutable external path): data_dir inside the frozen package, with
        # the themed SVG broom as the permanent in-code fallback.
        from ..utils import data_dir
        exe_icon_path = os.path.join(data_dir(), "assets", "limpiadora.ico")
        pm = QIcon(exe_icon_path).pixmap(34, 34) \
            if os.path.exists(exe_icon_path) else None
        if pm is not None and not pm.isNull():
            logo_icon.setPixmap(pm)
        else:
            logo_icon.setPixmap(icons.pixmap("clean", 34, role="accent"))
        logo_icon.setFixedSize(38, 38)
        logo_icon.setAlignment(Qt.AlignCenter)
        logo_row.addWidget(logo_icon)
        logo = QLabel(APP_NAME)
        logo.setObjectName("appLogo")
        logo_row.addWidget(logo)
        logo_row.addStretch(1)
        lay.addLayout(logo_row)
        lay.addSpacing(10)

        self.nav_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, i18n_key in _NAV:
            btn = QPushButton(t(i18n_key))
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(icons.nav(icons.NAV_ICONS[key]))
            btn.setIconSize(icons.icon_size())
            btn.clicked.connect(lambda _=False, k=key: self.show_page(k))
            group.addButton(btn)
            lay.addWidget(btn)
            self.nav_buttons[key] = btn

        lay.addStretch(1)
        # The theme (and every other preference) lives in the Settings page:
        # the sidebar keeps navigation only.
        return frame

    def apply_theme(self) -> None:
        """Apply the current theme and refresh every themed icon."""
        theme = self.settings.theme
        dark = {"dark": True, "light": False, "system": None}[theme]
        ui_theme.apply_theme(QApplication.instance(), dark=dark)
        # Keep the Settings selectors in sync (the theme is chosen there).
        settings_page = self._pages.get("settings")
        if settings_page is not None:
            settings_page.refresh_from_settings()
        # Re-render nav + page icons in the new palette.
        for key, btn in self.nav_buttons.items():
            btn.setIcon(icons.nav(icons.NAV_ICONS[key]))
        for page in self._pages.values():
            refresh = getattr(page, "refresh_icons", None)
            if refresh is not None:
                try:
                    refresh()
                except Exception as e:
                    _errlog(f"refresh_icons failed "
                            f"({type(page).__name__}): {e!r}")

    def showEvent(self, event) -> None:
        """Start the deferred winapp load and the first auto-analysis once
        the window has painted."""
        super().showEvent(event)
        if not self._winapp_ready:
            QTimer.singleShot(0, self._startup_winapp_load)
        if self.settings.auto_analyze and not self._auto_analyze_done:
            self._auto_analyze_done = True
            QTimer.singleShot(constants.ANALYZE_DEFER_MS,
                              self._auto_analyze_startup)

    def _auto_analyze_startup(self) -> None:
        """Incremental startup analysis (perf: skip redundant full scan).

        When the on-disk cache is still fresh, the cached sizes stand in
        for the scan: the UI paints the same numbers instantly and no
        disk walk happens at all. Stale or missing cache keeps the old
        behavior (full analysis). A manual Analyze always rescans."""
        if self.busy:
            # The deferred winapp load keeps the controller busy for a few
            # hundred ms. If this timer fires inside that window the scan
            # must be QUEUED, not dropped: dropping it left every row at 0
            # until the user pressed Analyze by hand.
            if not self._winapp_ready and self._winapp_load_is_startup:
                self._auto_analyze_pending = True
            return
        cache = self.controller.cache_service
        if self._cache_is_usable():
            self._apply_cache()
            self.pages_clean.update_total()
            age = cache.age_seconds() or 0.0
            self.set_status(t("status.cached",
                              age=humanize_duration(age)))
            _errlog("qt: startup used the fresh cache (no scan)")
            return
        if not self._winapp_ready:
            # The rules are still loading on the worker: without them the
            # winapp row would measure 0 and never be refreshed. Wait.
            self._auto_analyze_pending = True
            return
        _errlog("qt: startup analysis begins")
        self.analyze_all()

    def _cache_is_usable(self) -> bool:
        """True when the on-disk cache can stand in for a real scan.

        Freshness alone is not enough: a payload that describes none of the
        current categories (a foreign or test-written file) would make the
        UI skip the analysis and show nothing at all.
        """
        service = self.controller.cache_service
        if not service.is_fresh():
            return False
        cached = service.load()
        keys = {c.key for c in self.controller.categories}
        return bool(keys.intersection(cached))

    def _startup_winapp_load(self) -> None:
        """Load the bundled winapp2.ini after the first paint (E2.1).

        The parse + detection pass probes thousands of registry keys and
        paths (0.2-0.5 s on Windows); doing it inside controller
        construction delayed every startup's first frame. Runs
        unconditionally: the rules are needed even when auto-analysis is
        disabled."""
        if self._winapp_ready:
            return
        cat = next((c for c in self.controller.categories
                    if c.key == "winapp"), None)
        if cat is None or cat.rules:
            # No winapp category (injected test controllers) or the
            # controller already parsed the ini synchronously.
            self._winapp_ready = True
            self._maybe_run_pending_analysis()
            return
        if self.controller.busy:
            # Something else went busy first (e.g. an immediate refresh):
            # retry briefly, then give up (rules can still be loaded
            # manually from the clean page).
            if self._winapp_retries < 20:
                self._winapp_retries += 1
                QTimer.singleShot(100, self._startup_winapp_load)
            return
        self._winapp_load_is_startup = True
        self.controller.load_winapp_rules(default_winapp_file())

    def _maybe_run_pending_analysis(self) -> None:
        """Run the auto-analysis that was waiting for the winapp rules."""
        if self._auto_analyze_pending:
            self._auto_analyze_pending = False
            self._auto_analyze_startup()

    # -------------------------------------------------------- navigation

    def _get_page(self, key: str) -> QWidget:
        """Return the page for `key`, building it lazily on first use.

        Args:
            key: The page identifier (e.g., "clean", "startup").

        Returns:
            QWidget: The page widget.
        """
        page = self._pages.get(key)
        if page is None:
            if key == "clean":
                page = CleanPage(self)
            elif key == "startup":
                page = StartupPage(self)
            elif key == "dupes":
                page = DuplicatePage(self)
            elif key == "update":
                page = UpdatePage(self)
            elif key == "uninstall":
                page = UninstallPage(self)
            elif key == "settings":
                page = SettingsPage(self)
            else:
                page = LogPage(self)
            self._pages[key] = page
            self.stack.addWidget(page)
        return page

    def show_page(self, key: str) -> None:
        """Navigate to the specified page.

        Args:
            key: The page identifier.
        """
        page = self._get_page(key)
        self.stack.setCurrentWidget(page)
        self._current_key = key
        btn = self.nav_buttons.get(key)
        if btn is not None:
            btn.setChecked(True)
        on_show = getattr(page, "on_show", None)
        if on_show is not None:
            on_show()

    def rebuild_for_language(self, page_key: str | None = None) -> MainWindow:
        """Recreate the window so every label uses the new language.

        Labels resolve t() when they are built, so switching the language at
        runtime requires rebuilding the interface. The controller (and any
        running work) is shared with the new window, and the geometry and
        current page are preserved, so the change looks instantaneous.

        Args:
            page_key: Page to show in the new window (default: the current).

        Returns:
            MainWindow: The new window (the caller's window is closed).
        """
        page = page_key or getattr(self, "_current_key", "clean")
        geometry = self.geometry()
        self._closing = True          # skip the busy-cancel close handshake
        self.setAttribute(Qt.WA_DeleteOnClose, True)  # free the old window
        new_window = MainWindow(settings=self.settings,
                                controller=self.controller)
        new_window.setGeometry(geometry)
        new_window.show()
        new_window.show_page(page)
        self.close()
        return new_window

    @property
    def pages_clean(self) -> CleanPage:
        """The CleanPage instance."""
        page = self._get_page("clean")
        assert isinstance(page, CleanPage), "page registry changed: 'clean'"
        return page

    @property
    def categories(self):
        """The live category list (owned by the controller)."""
        return self.controller.categories

    @property
    def pages_dupes(self) -> DuplicatePage:
        """The DuplicatePage instance."""
        page = self._get_page("dupes")
        assert isinstance(page, DuplicatePage), "page registry changed: 'dupes'"
        return page

    @property
    def log_page(self) -> LogPage:
        """The LogPage instance."""
        page = self._get_page("log")
        assert isinstance(page, LogPage), "page registry changed: 'log'"
        return page

    # -------------------------------------------------- host API (pages)

    def log(self, msg: str) -> None:
        """Append a message to the application log.

        Args:
            msg: The log message string.
        """
        self.log_page.log(msg)

    def set_status(self, text: str) -> None:
        """Update the status bar text.

        Args:
            text: The status message to display.
        """
        self.pages_clean.status_lbl.setText(text)

    def set_busy(self, value: bool, mode: str = "determinate") -> None:
        """Set the global busy flag, drive the progress bar and notify
        every built page (on_busy) so they disable their action buttons.

        Args:
            value: True to show busy state, False to hide.
            mode: "determinate" (known progress) or "indeterminate" (unknown).
        """
        self.busy = value
        bar = self.pages_clean.progress
        if value:
            bar.setRange(0, 0) if mode == "indeterminate" \
                else bar.setRange(0, 1000)
        else:
            bar.setRange(0, 1000)
            bar.setValue(1000)
        for page in self._pages.values():
            handler = getattr(page, "on_busy", None)
            if handler is not None:
                try:
                    handler(value)
                except Exception as e:
                    _errlog(f"on_busy failed ({type(page).__name__}): {e!r}")

    def request_cancel(self) -> None:
        """Request cancellation of the current background operation."""
        self.controller.cancel()

    def update_total(self) -> None:
        """Recalculate and display the total size/files to clean."""
        self.pages_clean.update_total()

    # ------------------------------------------------------------ flows

    def _apply_cache(self) -> None:
        """Show cached sizes immediately (instant startup).

        The rows are refreshed too: without it the cached numbers only
        reached the total label and every category row kept its placeholder
        (the fresh-cache path never emits category_updated).
        """
        cached = self.controller.cache_service.load()
        for cat in self.controller.categories:
            entry = cached.get(cat.key)
            if isinstance(entry, dict) and isinstance(entry.get("size"),
                                                       (int, float)):
                cat.size = int(entry.get("size", 0))
                cat.files = int(entry.get("files", 0))
        self.pages_clean.refresh_results()

    def analyze_all(self) -> None:
        """Initiate a full analysis of all categories."""
        if self.busy:
            return
        self._apply_cache()
        self.pages_clean.progress.setValue(0)
        self.set_busy(True)
        self.set_status(t("status.analyzing"))
        self.controller.analyze()

    def confirm_clean(self) -> None:
        """Show the structured confirmation dialog and clean if approved."""
        from .messages import clean_confirmation
        selected = self.pages_clean.selected_categories()
        if not selected:
            app_info(self, "info", APP_NAME, t("msg.no_categories"))
            return
        to_recycle = bool(getattr(self.settings, "delete_to_recycle_bin",
                                  False))
        if not structured_confirm(self, "warning",
                                  *clean_confirmation(selected,
                                                      to_recycle=to_recycle),
                                  yes_text=t("btn.clean_yes")):
            return
        self.pages_clean.progress.setValue(0)
        self.set_status(t("status.cleaning"))
        self.controller.clean([c.key for c in selected],
                              to_recycle=to_recycle)

    def _on_recycle_toggled(self, on: bool) -> None:
        """Persist the recycle-bin-instead-of-delete preference."""
        self.settings.delete_to_recycle_bin = bool(on)
        self.settings.save()

    def preview_clean(self) -> None:
        """Collect preview file lists for selected categories."""
        selected = self.pages_clean.selected_categories()
        if not selected:
            app_info(self, "info", APP_NAME, t("msg.no_categories"))
            return
        if (sum(c.files for c in selected) == 0
                and not any(c.recycle_bin for c in selected)):
            app_info(self, "info", APP_NAME, t("msg.preview_empty"))
            return
        self.set_busy(True, mode="indeterminate")
        self.controller.preview([c.key for c in selected], limit=1000)

    def load_winapp_rules(self) -> None:
        """Open file dialog and load winapp2.ini rules."""
        path, _f = QFileDialog.getOpenFileName(
            self, t("dialog.winapp_title"), "",
            f"{t('dialog.winapp_filter')} (*.ini);;"
            f"{t('dialog.all_files')} (*.*)")
        if not path:
            return
        self.set_busy(True, mode="indeterminate")
        self.set_status(t("status.parsing_winapp"))
        self._winapp_load_is_startup = False
        self.controller.load_winapp_rules(path)

    # ------------------------------------------------- controller wiring

    def _wire_controller(self) -> None:
        """Connect controller signals to window slots."""
        c = self.controller
        c.busy_changed.connect(self._on_controller_busy)
        c.analysis_started.connect(
            lambda: self.set_status(t("status.analyzing")))
        c.analysis_progress.connect(self._on_analysis_progress)
        c.category_updated.connect(self.pages_clean.on_category_updated)
        c.analysis_finished.connect(
            lambda: self.set_status(t("status.analysis_done")))
        c.analysis_cancelled.connect(
            lambda: self.set_status(t("status.analyze_cancelled")))
        c.preview_started.connect(
            lambda: self.set_busy(True, mode="indeterminate"))
        c.preview_done.connect(self._on_preview_done)
        c.preview_error.connect(self._on_preview_error)
        c.clean_started.connect(
            lambda: self.set_status(t("status.cleaning")))
        c.clean_progress.connect(self._on_clean_progress)
        c.clean_log.connect(self._on_clean_log)
        c.clean_finished.connect(self._on_clean_finished)
        c.clean_cancelled.connect(
            lambda: self.set_status(t("status.clean_cancelled")))
        c.winapp_loaded.connect(self._on_winapp_loaded)
        c.winapp_error.connect(self._on_winapp_error)
        c.operation_error.connect(self._on_operation_error)

    def _on_controller_busy(self, busy: bool) -> None:
        self.set_busy(busy)

    def _on_analysis_progress(self, label: str, frac: float) -> None:
        self.set_status(f"{t('status.analyzing')} {label} ...")
        self.pages_clean.progress.setRange(0, 1000)
        self.pages_clean.progress.setValue(int(max(0.0, min(frac, 1.0)) * 1000))

    def _on_clean_progress(self, frac: float) -> None:
        self.pages_clean.progress.setRange(0, 1000)
        self.pages_clean.progress.setValue(int(max(0.0, min(frac, 1.0)) * 1000))

    def _on_clean_log(self, msg: str) -> None:
        if msg.startswith("cleaning:"):
            self.set_status(t("log.cleaning_cat", label=msg.split(":", 1)[1]))
        elif msg.startswith("cleaned:"):
            # maxsplit=4: a category label containing ':' must not break
            # the (kind, label, removed, errors, freed) unpacking.
            _kind, _label, r, e, f = msg.split(":", 4)
            self.log(t("log.cat_cleaned", n=r, e=e, size=format_size(int(f))))
        elif msg.startswith("recycle:"):
            # recycle:{label}:ok | recycle:{label}:<failure message>
            parts = msg.split(":", 2)
            text = (t("msg.recycle_emptied")
                    if len(parts) > 2 and parts[2] == "ok"
                    else (parts[2] if len(parts) > 2 else ""))
            self.log(t("log.recycle_line", msg=text))

    def _on_clean_finished(self, summary: CleanSummary) -> None:
        self.log(t("log.total_freed", size=format_size(summary.freed)))
        self.set_status(t("status.clean_done",
                          size=format_size(summary.freed)))
        # Refresh the rows from the post-clean sizes (no re-scan needed:
        # the categories were updated in place).
        for cat in self.controller.categories:
            self.pages_clean.on_category_updated(cat.key)

    def _on_preview_done(self, data) -> None:
        labels = {c.key: c.label for c in self.controller.categories}
        recycle = {c.key for c in self.controller.categories
                   if c.recycle_bin}
        lines: list[str] = []
        for key, files, scanned in data:
            label = labels.get(key, key)
            if key in recycle:
                lines.append(t("preview.recycle_section", label=label)
                             + "\n\n")
                continue
            lines.append(t("preview.section", label=label,
                           shown=len(files), total=scanned) + "\n")
            lines.extend(f"  {f}" for f in files)
            lines.append("\n")
        win, box = readonly_toplevel(self, t("title.preview"), "760x520",
                                     t("preview.header"))
        box.setReadOnly(False)
        box.setPlainText("".join(lines))
        box.setReadOnly(True)
        win.exec()

    def _on_preview_error(self, message: str) -> None:
        app_info(self, "critical", APP_NAME,
                 t("msg.preview_error", exc=message))

    def _on_winapp_loaded(self, count: int) -> None:
        self._winapp_ready = True
        self.pages_clean._build_rows()
        self.set_status(t("status.winapp_loaded", n=count))
        self.log(t("log.winapp_loaded", n=count, path=""))
        if self._winapp_load_is_startup:
            # Deferred startup load: analyze ONLY if the auto-analysis is
            # still waiting for these rules (fresh cache already painted
            # its numbers; auto_analyze off means no scan at all).
            self._maybe_run_pending_analysis()
        else:
            # Manual load from the clean page: refresh the analysis, as
            # this handler always did before E2.1.
            self.analyze_all()

    def _on_winapp_error(self, message: str) -> None:
        self._winapp_ready = True
        self.set_status(t("status.winapp_error"))
        app_info(self, "critical", APP_NAME,
                 t("msg.winapp_error", exc=message))
        self._maybe_run_pending_analysis()

    def _on_operation_error(self, message: str) -> None:
        _errlog(f"operation error: {message}")
        self.set_status(t("msg.error_simple", exc=message))

    # ------------------------------------------------------------ events

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cancel any running operation before closing (cooperative).

        This ensures that background threads are not abruptly terminated
        while holding file handles or locks.

        Args:
            event: The close event.
        """
        if self.controller.busy and not self._closing:
            self._closing = True
            self.controller.cancel()
            self.set_status(t("status.clean_cancelled"))
            event.ignore()
            self.controller.busy_changed.connect(self._close_when_idle)
            return
        event.accept()

    def _close_when_idle(self, busy: bool) -> None:
        """Close the window once the controller is idle."""
        if not busy:
            self.controller.busy_changed.disconnect(self._close_when_idle)
            self.close()
