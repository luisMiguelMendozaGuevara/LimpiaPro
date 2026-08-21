"""Preview dialog: the files that would be deleted, per category."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import t


class PreviewDialog(QDialog):
    """Readonly listing of the collected targets (first `limit` per
    category). The collection itself happened on a worker thread; this
    dialog only renders the result."""

    def __init__(self, data: list[tuple[str, list[str], int]],
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(t("title.preview"))
        self.resize(760, 520)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(10)

        header = QLabel(t("preview.header"))
        header.setObjectName("cardTitle")
        lay.addWidget(header)

        box = QPlainTextEdit()
        box.setReadOnly(True)
        lines: list[str] = []
        for key, files, scanned in data:
            lines.append(f"== {key} ({len(files)} shown of {scanned} detected) ==")
            lines.extend(f"  {f}" for f in files)
            lines.append("")
        box.setPlainText("\n".join(lines))
        lay.addWidget(box, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton(t("btn.cancel"))
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        lay.addLayout(buttons)
