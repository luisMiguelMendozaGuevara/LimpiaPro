"""Destructive-action confirmation dialog (Fase 6: Confirmar)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...controller import CategoryResult
from ...i18n import t
from ...utils import format_size


class ConfirmCleanDialog(QDialog):
    """Shows the selected categories and their total size before the
    deletion is requested; the actual safety validation still happens in
    the core (SafetyGuard), never here."""

    def __init__(self, selected: list[CategoryResult], total: int,
                 needs_admin: bool, includes_recycle: bool,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(t("app.window_subtitle"))
        self.setMinimumWidth(480)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)

        title = QLabel(t("clean.title"))
        title.setObjectName("cardTitle")
        lay.addWidget(title)

        names = "\n".join(f"  \u2022 {c.label}" for c in selected)
        detail = t("msg.clean_detail_base")
        if includes_recycle:
            detail += t("msg.clean_detail_recycle")
        if needs_admin:
            detail += t("msg.clean_detail_admin")

        body = QLabel(
            t("msg.clean_confirm", names=names,
              size=format_size(total), detail=detail))
        body.setWordWrap(True)
        lay.addWidget(body)

        warning = QLabel(t("clean.safety_note"))
        warning.setObjectName("cardDesc")
        warning.setWordWrap(True)
        lay.addWidget(warning)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(t("btn.cancel"))
        cancel.clicked.connect(self.reject)
        clean = QPushButton(t("btn.clean_selected"))
        clean.setProperty("kind", "danger")
        clean.setDefault(True)
        clean.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(clean)
        lay.addLayout(buttons)
