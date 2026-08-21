"""Page: Inicio (dashboard)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import t
from ...utils import format_size
from ..widgets import StatCard


class HomePage(QWidget):
    """Dashboard: quick stats, the analyze action and navigation."""

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(16)

        title = QLabel(t("home.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("home.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.junk_card = StatCard(t("home.stat_junk"))
        self.cats_card = StatCard(t("home.stat_categories"))
        self.last_card = StatCard(t("home.stat_status"))
        for card in (self.junk_card, self.cats_card, self.last_card):
            stats.addWidget(card, 1)
        lay.addLayout(stats)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.analyze_btn = QPushButton(t("home.btn_analyze"))
        self.analyze_btn.setProperty("kind", "primary")
        self.analyze_btn.setMinimumHeight(40)
        self.analyze_btn.clicked.connect(self._on_analyze)
        actions.addWidget(self.analyze_btn)
        self.go_clean_btn = QPushButton(t("home.btn_go_clean"))
        self.go_clean_btn.clicked.connect(lambda: self.host.navigate("clean"))
        actions.addWidget(self.go_clean_btn)
        self.go_results_btn = QPushButton(t("home.btn_go_results"))
        self.go_results_btn.clicked.connect(lambda: self.host.navigate("results"))
        actions.addWidget(self.go_results_btn)
        actions.addStretch(1)
        lay.addLayout(actions)

        note = QLabel(t("home.safety_note"))
        note.setObjectName("cardDesc")
        note.setWordWrap(True)
        note.setAlignment(Qt.AlignLeft)
        lay.addWidget(note)
        lay.addStretch(1)

    # ------------------------------------------------------------ actions

    def _on_analyze(self) -> None:
        self.host.controller.analyze()

    def on_busy(self, busy: bool) -> None:
        self.analyze_btn.setEnabled(not busy)

    def on_show(self) -> None:
        """Refresh the dashboard stats when the page becomes visible."""
        results = self.host.controller.get_results()
        total = sum(r.size for r in results)
        files = sum(r.files for r in results)
        self.junk_card.set_value(format_size(total))
        self.cats_card.set_value(str(len(results)))
        self.last_card.set_value(
            t("home.stat_files", n=f"{files:,}") if files else "-")
