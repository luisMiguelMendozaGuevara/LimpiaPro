"""Page: activity log (replica of the legacy log page)."""

from __future__ import annotations

import time

from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from ...i18n import t


class LogPage(QWidget):
    """Readonly monospace view of everything the app has done this session.

    host.log() forwards every message here; each line is timestamped with
    HH:MM:SS."""

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
        """Append one timestamped line to the log view."""
        self.text.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")
        bar = self.text.verticalScrollBar()
        bar.setValue(bar.maximum())
