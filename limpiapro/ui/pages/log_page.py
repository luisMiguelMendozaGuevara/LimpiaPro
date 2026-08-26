"""Page: activity log 

This module implements a simple read-only log viewer for the PySide6
interface. It displays a timestamped history of all application events
for the current session.

Design Principles:
1. Simplicity: A single QPlainTextEdit with auto-scroll.
2. Performance: Uses appendPlainText for efficient text insertion.
3. Read-Only: Prevents accidental modification of the log.
"""

from __future__ import annotations

import time

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ...i18n import t


class LogPage(QWidget):
    """Readonly monospace view of everything the app has done this session.

    host.log() forwards every message here; each line is timestamped with
    HH:MM:SS.

    Attributes:
        host: The main window host.
        text: The QPlainTextEdit widget displaying the log.
    """

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(8)

        title = QLabel(t("logpage.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        lay.addWidget(self.text, 1)

    def log(self, msg: str) -> None:
        """Append one timestamped line to the log view.

        Args:
            msg: The log message string.
        """
        self.text.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")
        # Auto-scroll to the bottom to show the newest entry.
        bar = self.text.verticalScrollBar()
        bar.setValue(bar.maximum())
