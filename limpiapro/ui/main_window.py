"""LimpiaPro main window (PySide6 replica of the legacy CleanerApp).

Sidebar navigation with the same six pages (Limpieza, Inicio, Duplicados,
Windows Update, Desinstalar, Registro), a lazily built QStackedWidget and
the same host surface the legacy pages used (busy, set_busy, set_status,
log, categories, confirm_clean, ...). The clean-page flows run through
the LimpiaProController workers; the other pages use run_async."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..controller import CleanSummary, LimpiaProController
from ..i18n import t
from ..settings import Settings
from ..utils import _errlog, format_size, is_admin
from . import theme as ui_theme
from .pages import (
    CleanPage,
    DuplicatePage,
    LogPage,
    StartupPage,
    UninstallPage,
    UpdatePage,
)
from .widgets import readonly_toplevel

_NAV = [
    ("clean", "nav.clean"),
    ("startup", "nav.startup"),
    ("dupes", "nav.dupes"),
    ("update", "nav.update"),
    ("uninstall", "nav.uninstall"),
    ("log", "nav.log"),
]


class MainWindow(QMainWindow):
    """Application window: sidebar navigation, pages and global state."""

    def __init__(self, settings: Settings | None = None,
                 controller: LimpiaProController | None = None):
        super().__init__()
        self.settings = (settings or Settings.load()).validate()
        self.controller = controller or LimpiaProController()
        self.busy = False
        self.scanner = None
        self._pages: dict[str, QWidget] = {}
        self._closing = False

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} - {t('app.window_subtitle')}")
        self.resize(1000, 680)
        self.setMinimumSize(860, 560)

        self._build_ui()
        self._wire_controller()
        ui_theme.apply_mica_backdrop(self)
        self.apply_theme()
        self.show_page("clean")

        self.log(t("log.started_admin" if is_admin() else "log.started_no_admin",
                   app=APP_NAME, ver=APP_VERSION))
        if self.settings.auto_analyze:
            # Deferred so the window paints before the scan starts.
            QTimer.singleShot(300, self.analyze_all)
        _errlog("qt: window created")

    # ------------------------------------------------------------- layout

    def _build_ui(self) -> None:
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
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(200)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 16, 10, 14)
        lay.setSpacing(4)

        logo = QLabel(f"\U0001F9F9  {APP_NAME}")
        logo.setObjectName("appLogo")
        lay.addWidget(logo)
        lay.addSpacing(10)

        self.nav_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, i18n_key in _NAV:
            btn = QPushButton(t(i18n_key))
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self.show_page(k))
            group.addButton(btn)
            lay.addWidget(btn)
            self.nav_buttons[key] = btn

        lay.addStretch(1)

        # Sidebar footer: light/dark toggle.
        self.theme_toggle = QCheckBox(t("theme.dark"))
        self.theme_toggle.setChecked(
            self.settings.theme != "light")
        self.theme_toggle.toggled.connect(self._on_theme_toggled)
        lay.addWidget(self.theme_toggle)
        return frame

    def _on_theme_toggled(self, dark: bool) -> None:
        self.settings.theme = "dark" if dark else "light"
        self.settings.save()
        self.apply_theme()

    def apply_theme(self) -> None:
        theme = self.settings.theme
        dark = {"dark": True, "light": False, "system": None}[theme]
        ui_theme.apply_theme(QApplication.instance(), dark=dark)
        self.theme_toggle.setText(
            t("theme.dark") if dark else t("theme.light"))

    # -------------------------------------------------------- navigation

    def _get_page(self, key: str) -> QWidget:
        """Return the page for `key`, building it lazily on first use."""
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
            else:
                page = LogPage(self)
            self._pages[key] = page
            self.stack.addWidget(page)
        return page

    def show_page(self, key: str) -> None:
        page = self._get_page(key)
        self.stack.setCurrentWidget(page)
        btn = self.nav_buttons.get(key)
        if btn is not None:
            btn.setChecked(True)
        on_show = getattr(page, "on_show", None)
        if on_show is not None:
            on_show()

    @property
    def pages_clean(self) -> CleanPage:
        return self._get_page("clean")

    @property
    def categories(self):
        """The live category list (owned by the controller)."""
        return self.controller.categories

    @property
    def pages_dupes(self) -> DuplicatePage:
        return self._get_page("dupes")

    @property
    def log_page(self) -> LogPage:
        return self._get_page("log")

    # -------------------------------------------------- host API (pages)

    def log(self, msg: str) -> None:
        self.log_page.log(msg)

    def set_status(self, text: str) -> None:
        self.pages_clean.status_lbl.setText(text)

    def set_busy(self, value: bool, mode: str = "determinate") -> None:
        """Set the global busy flag, drive the progress bar and notify
        every built page (on_busy) so they disable their action buttons."""
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
        self.controller.cancel()

    def update_total(self) -> None:
        self.pages_clean.update_total()

    # ------------------------------------------------------------ flows

    def _apply_cache(self) -> None:
        """Show cached sizes immediately (instant startup)."""
        cached = self.controller.cache_service.load()
        for cat in self.controller.categories:
            entry = cached.get(cat.key)
            if isinstance(entry, dict) and isinstance(entry.get("size"),
                                                       (int, float)):
                cat.size = int(entry.get("size", 0))
                cat.files = int(entry.get("files", 0))

    def analyze_all(self) -> None:
        if self.busy:
            return
        self._apply_cache()
        self.pages_clean.progress.setValue(0)
        self.set_busy(True)
        self.set_status(t("status.analyzing"))
        self.controller.analyze()

    def confirm_clean(self) -> None:
        selected = self.pages_clean.selected_categories()
        if not selected:
            QMessageBox.information(self, APP_NAME, t("msg.no_categories"))
            return
        total = sum(c.size for c in selected)
        names = "\n".join(f"  \u2022 {c.label}" for c in selected)
        detail = t("msg.clean_detail_base")
        if any(c.recycle_bin for c in selected):
            detail += t("msg.clean_detail_recycle")
        if any(c.needs_admin for c in selected) and not is_admin():
            detail += t("msg.clean_detail_admin")
        msg = t("msg.clean_confirm", names=names, size=format_size(total),
                detail=detail)
        box = QMessageBox(QMessageBox.Warning, APP_NAME, msg,
                          QMessageBox.Yes | QMessageBox.No, self)
        if box.exec() != QMessageBox.Yes:
            return
        self.pages_clean.progress.setValue(0)
        self.set_status(t("status.cleaning"))
        self.controller.clean([c.key for c in selected])

    def preview_clean(self) -> None:
        selected = self.pages_clean.selected_categories()
        if not selected:
            QMessageBox.information(self, APP_NAME, t("msg.no_categories"))
            return
        if (sum(c.files for c in selected) == 0
                and not any(c.recycle_bin for c in selected)):
            QMessageBox.information(self, APP_NAME, t("msg.preview_empty"))
            return
        self.set_busy(True, mode="indeterminate")
        self.controller.preview([c.key for c in selected], limit=1000)

    def load_winapp_rules(self) -> None:
        path, _f = QFileDialog.getOpenFileName(
            self, t("dialog.winapp_title"), "",
            f"{t('dialog.winapp_filter')} (*.ini);;"
            f"{t('dialog.all_files')} (*.*)")
        if not path:
            return
        self.set_busy(True, mode="indeterminate")
        self.set_status(t("status.parsing_winapp"))
        self.controller.load_winapp_rules(path)

    # ------------------------------------------------- controller wiring

    def _wire_controller(self) -> None:
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
            _kind, label, r, e, f = msg.split(":")
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
        QMessageBox.critical(self, APP_NAME,
                             t("msg.preview_error", exc=message))

    def _on_winapp_loaded(self, count: int) -> None:
        self.pages_clean._build_rows()
        self.set_status(t("status.winapp_loaded", n=count))
        self.log(t("log.winapp_loaded", n=count, path=""))
        self.analyze_all()

    def _on_winapp_error(self, message: str) -> None:
        self.set_status(t("status.winapp_error"))
        QMessageBox.critical(self, APP_NAME,
                             t("msg.winapp_error", exc=message))

    def _on_operation_error(self, message: str) -> None:
        _errlog(f"operation error: {message}")
        self.set_status(t("msg.error_simple", exc=message))

    # ------------------------------------------------------------ events

    def closeEvent(self, event: QCloseEvent) -> None:
        """Cancel any running operation before closing (cooperative)."""
        if self.controller.busy and not self._closing:
            self._closing = True
            self.controller.cancel()
            self.set_status(t("status.clean_cancelled"))
            event.ignore()
            self.controller.busy_changed.connect(self._close_when_idle)
            return
        event.accept()

    def _close_when_idle(self, busy: bool) -> None:
        if not busy:
            self.controller.busy_changed.disconnect(self._close_when_idle)
            self.close()
