"""Main window: sidebar navigation + QStackedWidget pages + status bar.

Owns the LimpiaProController and wires its signals to the pages and the
global status bar. The pages only talk to the controller through the
small host surface exposed here (navigate, set_status, set_progress,
preview_flow, apply_settings, controller, settings)."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME, APP_VERSION
from ..controller import CleanSummary, LimpiaProController
from ..i18n import set_language, t
from ..settings import Settings
from ..utils import _errlog, format_size
from . import theme as ui_theme
from .pages import CleanPage, HomePage, ResultsPage, SettingsPage

_NAV = [
    ("home", "nav.home"),
    ("clean", "nav.clean"),
    ("results", "nav.results"),
    ("settings", "nav.settings"),
]


class MainWindow(QMainWindow):
    """Application window (PySide6)."""

    def __init__(self, settings: Settings | None = None,
                 controller: LimpiaProController | None = None):
        super().__init__()
        self.settings = (settings or Settings.load()).validate()
        if self.settings.language != "auto":
            set_language(self.settings.language)
        self.controller = controller or LimpiaProController()
        self._closing = False

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} - {t('app.window_subtitle')}")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)

        self._build_ui()
        self._wire_controller()
        self.apply_settings()

        if self.settings.auto_analyze:
            # Deferred so the window paints before the scan starts.
            QTimer.singleShot(250, self.controller.analyze)
        _errlog("qt: window created")

    # ------------------------------------------------------------- layout

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {
            "home": HomePage(self),
            "clean": CleanPage(self),
            "results": ResultsPage(self),
            "settings": SettingsPage(self),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        root.addWidget(self.sidebar)
        root.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        # Status bar: progress + status text (global, always visible).
        bar = self.statusBar()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFixedWidth(220)
        self.progress.setVisible(False)
        self.status_lbl = QLabel(t("status.ready"))
        self.status_lbl.setObjectName("statusText")
        bar.addPermanentWidget(self.status_lbl, 1)
        bar.addPermanentWidget(self.progress)

        self.navigate("home")

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("sidebar")
        frame.setFixedWidth(208)
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 18, 12, 14)
        lay.setSpacing(4)

        logo = QLabel(f"\U0001F9F9  {APP_NAME}")
        logo.setObjectName("appLogo")
        lay.addWidget(logo)
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("appVersion")
        lay.addWidget(version)
        lay.addSpacing(18)

        self.nav_buttons: dict[str, QPushButton] = {}
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key, i18n_key in _NAV:
            btn = QPushButton(t(i18n_key))
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            group.addButton(btn)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            lay.addWidget(btn)
            self.nav_buttons[key] = btn
        lay.addStretch(1)

        note = QLabel(t("home.safety_note"))
        note.setObjectName("appVersion")
        note.setWordWrap(True)
        lay.addWidget(note)
        return frame

    # -------------------------------------------------------- navigation

    def navigate(self, key: str) -> None:
        """Switch the visible page and highlight its nav button."""
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        btn = self.nav_buttons.get(key)
        if btn is not None:
            btn.setChecked(True)
        on_show = getattr(page, "on_show", None)
        if on_show is not None:
            on_show()

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

    # -------------------------------------------------- host API (pages)

    def preview_flow(self, keys: list[str]) -> None:
        self.controller.preview(keys)

    def set_status(self, text: str) -> None:
        self.status_lbl.setText(text)

    def set_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(value, 1.0)) * 1000))

    def apply_settings(self) -> None:
        """Apply the persisted settings (theme at least)."""
        theme = self.settings.theme
        dark = {"dark": True, "light": False, "system": None}[theme]
        ui_theme.apply_theme(QApplication.instance(), dark=dark)

    # ------------------------------------------------- controller wiring

    def _wire_controller(self) -> None:
        c = self.controller
        c.busy_changed.connect(self._on_busy_changed)
        c.analysis_started.connect(
            lambda: self.set_status(t("status.analyzing")))
        c.analysis_progress.connect(self._on_analysis_progress)
        c.category_updated.connect(self.pages["clean"].on_category_updated)
        c.analysis_finished.connect(
            lambda: self.set_status(t("status.analysis_done")))
        c.analysis_finished.connect(self.pages["results"].refresh)
        c.analysis_cancelled.connect(
            lambda: self.set_status(t("status.analyze_cancelled")))
        c.preview_done.connect(self.pages["clean"].on_preview_done)
        c.preview_error.connect(self.pages["clean"].on_preview_error)
        c.clean_started.connect(
            lambda: self.set_status(t("status.cleaning")))
        c.clean_progress.connect(self.set_progress)
        c.clean_log.connect(self._on_clean_log)
        c.clean_finished.connect(self._on_clean_finished)
        c.clean_cancelled.connect(self._on_clean_cancelled)
        c.winapp_loaded.connect(self._on_winapp_loaded)
        c.winapp_error.connect(self._on_winapp_error)
        c.operation_error.connect(self._on_operation_error)

    def _on_busy_changed(self, busy: bool) -> None:
        self.progress.setVisible(busy)
        if not busy:
            self.progress.setValue(0)
            if not self._closing:
                self.set_status(t("status.ready"))
        for page in self.pages.values():
            on_busy = getattr(page, "on_busy", None)
            if on_busy is not None:
                on_busy(busy)

    def _on_analysis_progress(self, label: str, frac: float) -> None:
        self.set_status(f"{t('status.analyzing')} {label} ...")
        self.set_progress(frac)

    def _on_clean_log(self, msg: str) -> None:
        if msg.startswith("cleaning:"):
            self.set_status(t("log.cleaning_cat", label=msg.split(":", 1)[1]))
        elif msg.startswith("cleaned:"):
            _kind, label, r, e, f = msg.split(":")
            self.set_status(t("log.cat_cleaned", n=r, e=e,
                              size=format_size(int(f))))
        elif msg.startswith("recycle:"):
            self.set_status(t("status.cleaning"))

    def _on_clean_finished(self, summary: CleanSummary) -> None:
        self.pages["results"].on_clean_finished(summary)
        self.pages["clean"]._build_cards()
        self.set_status(t("status.clean_done", size=format_size(summary.freed)))
        self.navigate("results")

    def _on_clean_cancelled(self) -> None:
        self.pages["results"].on_clean_cancelled()
        self.set_status(t("status.clean_cancelled"))

    def _on_winapp_loaded(self, count: int) -> None:
        self.pages["clean"]._build_cards()
        self.set_status(t("status.winapp_loaded", n=count))

    def _on_winapp_error(self, message: str) -> None:
        self.set_status(t("status.winapp_error"))

    def _on_operation_error(self, message: str) -> None:
        _errlog(f"operation error: {message}")
        self.set_status(f"{t('msg.error_simple', exc=message)}")
