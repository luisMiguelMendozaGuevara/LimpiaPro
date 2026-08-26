"""Page: Windows Update leftovers (WinSxS / DISM) (replica of the legacy
update page).

This module implements the Windows Update cleanup UI for PySide6. It
wraps the DISM (Deployment Image Servicing and Management) command-line
tool to analyze and clean the WinSxS component store.

Architecture:
    - Measures the component store size (C:\\Windows\\WinSxS).
    - Runs DISM analyze/cleanup commands on a worker thread.
    - DISM output arrives in the operating system language (out of the
      app's control) and is appended verbatim to the console box.

Design Principles:
1. Safety: DISM is a system-level tool; all operations require admin.
2. Transparency: Raw DISM output is shown to the user.
3. Thread Safety: DISM runs on a background thread with a 30-minute timeout.
"""

from __future__ import annotations

import subprocess

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME
from ...i18n import t
from ...utils import _folder_size, format_size
from .. import constants, icons
from ..workers import run_async


class UpdatePage(QWidget):
    """WinSxS component store analyzer and cleaner (DISM wrapper).

    Attributes:
        host: The main window host.
        out: The QPlainTextEdit widget displaying DISM output.
        size_lbl: The label displaying the WinSxS folder size.
    """

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(8)

        title = QLabel(t("update.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("update.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.analyze_btn = QPushButton(t("btn.analyze"))
        self.analyze_btn.clicked.connect(self.analyze)
        self.clean_btn = QPushButton(t("btn.clean_updates"))
        self.clean_btn.setProperty("kind", "warning")
        self.clean_btn.clicked.connect(self.clean)
        self.size_lbl = QLabel(t("label.calculating"))
        self.size_lbl.setObjectName("mutedText")
        bar.addWidget(self.analyze_btn)
        bar.addWidget(self.clean_btn)
        bar.addStretch(1)
        bar.addWidget(self.size_lbl)
        lay.addLayout(bar)
        self._apply_button_icons()

        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        lay.addWidget(self.out, 1)

        # The constructor triggers the WinSxS measurement (the page is
        # built lazily on first visit, so this runs once, off the UI
        # thread).
        run_async(self, self._measure, self._measure_done,
                  on_error=self._measure_error)

    # ------------------------------------------------------------- state

    def _apply_button_icons(self) -> None:
        """Attach themed icons to the page buttons."""
        icons.apply(self.analyze_btn, "analyze")
        icons.apply(self.clean_btn, "shield", role="warning")

    def refresh_icons(self) -> None:
        """Re-apply every icon after a dark/light theme switch."""
        self._apply_button_icons()

    def on_busy(self, busy: bool) -> None:
        """Disable action buttons while an operation is running."""
        self.analyze_btn.setEnabled(not busy)
        self.clean_btn.setEnabled(not busy)

    def on_show(self) -> None:
        """Called when the page becomes visible."""
        pass

    # ---------------------------------------------------------- actions

    def _measure_error(self, exc) -> None:
        """Handle WinSxS measurement errors."""
        self.host.set_busy(False)
        self.size_lbl.setText(t("update.not_available"))
        self.host.log(t("log.winsxs_error", exc=exc))

    def _log_out(self, text: str) -> None:
        """Append text to the output console and auto-scroll."""
        self.out.appendPlainText(text)
        bar = self.out.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _measure(self):
        """Measure the size of the WinSxS folder."""
        return (_folder_size(r"C:\Windows\WinSxS"),)

    def _measure_done(self, size) -> None:
        """Handle WinSxS measurement completion."""
        self.size_lbl.setText(t("update.winsxs_size", size=format_size(size)))

    def _run_dism(self, args, label) -> None:
        """Run a DISM command with the given arguments."""
        if self.host.busy:
            return
        self.host.set_busy(True, mode="indeterminate")
        self._log_out(t("update.section", label=label))
        run_async(self, self._dism_worker, self._dism_done, (args,),
                  on_error=self._dism_error)

    def _dism_error(self, exc) -> None:
        """Handle DISM execution errors."""
        self.host.set_busy(False)
        self._log_out(t("update.error", exc=exc))

    def _dism_worker(self, args):
        """Run DISM with a 30-minute timeout and return its output.

        Note:
            The nosec B603 comment is required because Bandit flags
            subprocess.run with variable arguments. However, the binary
            is fixed ("dism") and the arguments are controlled by the
            application, so there is no injection risk.
        """
        try:
            result = subprocess.run(  # nosec B603 - fixed binary + arg list
                ["dism", "/online", "/cleanup-image", *args],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=constants.DISM_TIMEOUT_S,
                creationflags=subprocess.CREATE_NO_WINDOW)
            out = (result.stdout or result.stderr or "").strip()
        except Exception as e:
            out = t("update.error", exc=e)
        return (out,)

    def _dism_done(self, out) -> None:
        """Handle DISM command completion."""
        self.host.set_busy(False)
        self._log_out(out or t("update.no_output"))
        self._log_out(t("update.finished"))

    def analyze(self) -> None:
        """Analyze the component store for cleanup potential."""
        self._run_dism(["/AnalyzeComponentStore"], t("update.analyzing"))

    def clean(self) -> None:
        """Clean the component store after confirmation."""
        from ..dialogs import app_confirm
        if not app_confirm(self, "warning", APP_NAME,
                           t("msg.update_clean_confirm"),
                           yes_text=t("btn.clean_yes")):
            return
        self._run_dism(["/StartComponentCleanup"], t("update.cleaning"))
