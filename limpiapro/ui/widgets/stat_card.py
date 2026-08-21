"""Small stat card used on the home dashboard."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget


class StatCard(QFrame):
    """A titled value box (e.g. total junk, categories count)."""

    def __init__(self, title: str, value: str = "-",
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(2)
        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("statValue")
        self.value_lbl.setAlignment(Qt.AlignLeft)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("statLabel")
        lay.addWidget(self.value_lbl)
        lay.addWidget(self.title_lbl)

    def set_value(self, value: str) -> None:
        self.value_lbl.setText(value)
