"""One cleaning category card: checkbox, icon, labels and measured size."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ...controller import CategoryResult
from ...utils import format_size


class CategoryCard(QFrame):
    """Card row for one cleaning category in the Limpieza page."""

    toggled = Signal(str, bool)  # (category key, checked)

    def __init__(self, result: CategoryResult, checked: bool = True,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self._key = result.key

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)

        self.check = QCheckBox()
        self.check.setChecked(checked)
        lay.addWidget(self.check, 0, Qt.AlignTop)

        self.icon_lbl = QLabel(result.icon)
        self.icon_lbl.setFixedWidth(26)
        self.icon_lbl.setStyleSheet("font-size: 20px; background: transparent;")
        lay.addWidget(self.icon_lbl, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_lbl = QLabel(result.label)
        self.title_lbl.setObjectName("cardTitle")
        self.desc_lbl = QLabel(result.description)
        self.desc_lbl.setObjectName("cardDesc")
        self.desc_lbl.setWordWrap(True)
        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.desc_lbl)
        lay.addLayout(text_col, 1)

        right = QVBoxLayout()
        right.setSpacing(0)
        self.size_lbl = QLabel()
        self.size_lbl.setObjectName("cardSize")
        self.size_lbl.setAlignment(Qt.AlignRight)
        self.files_lbl = QLabel()
        self.files_lbl.setObjectName("cardFiles")
        self.files_lbl.setAlignment(Qt.AlignRight)
        right.addWidget(self.size_lbl)
        right.addWidget(self.files_lbl)
        lay.addLayout(right, 0)

        self.check.toggled.connect(
            lambda on, k=self._key: self.toggled.emit(k, on))
        self.set_result(result)

    # ------------------------------------------------------------ state

    @property
    def key(self) -> str:
        return self._key

    def is_checked(self) -> bool:
        return self.check.isChecked()

    def set_checked(self, value: bool) -> None:
        self.check.setChecked(value)

    def set_result(self, result: CategoryResult) -> None:
        """Refresh the displayed size/file count from a result row."""
        self.title_lbl.setText(result.label)
        self.desc_lbl.setText(result.description)
        self.icon_lbl.setText(result.icon)
        if result.recycle_bin:
            txt = f"~{format_size(result.size)}" if result.size else ""
            files = ""
        else:
            txt = format_size(result.size) if result.size else ""
            files = f"{result.files:,} files" if result.files else ""
        self.size_lbl.setText(txt)
        self.files_lbl.setText(files)
        self.setToolTip(result.description)

    def set_status(self, text: str, kind: str = "muted") -> None:
        """Override the size label with a transient status (calculating...,
        clean, etc.). kind: muted|success|error."""
        color = {"success": "#34a853", "error": "#ea4335"}.get(kind, "#9aa0a6")
        self.size_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self.size_lbl.setText(text)
