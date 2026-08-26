"""EmptyState: centered icon + text placeholder for empty lists."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class EmptyState(QWidget):
    """Centered icon + muted-text placeholder shown when a list is empty.

    Attributes:
        icon_lbl: The QLabel holding the themed icon pixmap.
        text_lbl: The muted description label.
    """

    def __init__(self, icon_name: str, text: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._icon_name = icon_name
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon_lbl)
        self.text_lbl = QLabel(text)
        self.text_lbl.setObjectName("pageSubtitle")
        self.text_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.text_lbl)
        lay.addStretch(1)
        self.refresh_icon()

    def refresh_icon(self) -> None:
        """Re-render the pixmap (after a dark/light switch)."""
        from . import icons
        pm = icons.pixmap(self._icon_name, 44, role="faint")
        self.icon_lbl.setPixmap(pm)
