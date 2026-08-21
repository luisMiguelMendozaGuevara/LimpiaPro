"""Page: Resultados (analysis results and final clean outcome)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...controller import CleanSummary
from ...i18n import t
from ...utils import format_size


class ResultsPage(QWidget):
    """Shows the per-category analysis results and, after a clean, the
    final outcome (Fase 6: Resultado final). No re-scan happens here: the
    controller already updated the category sizes in place."""

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        self._last_summary: CleanSummary | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        title = QLabel(t("results.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("results.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        # ------------------------------------------------ summary panel
        self.summary_lbl = QLabel("")
        self.summary_lbl.setObjectName("successText")
        self.summary_lbl.setWordWrap(True)
        self.summary_lbl.hide()
        lay.addWidget(self.summary_lbl)

        # --------------------------------------------------------- table
        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels([
            t("col.name"), t("col.size"), t("results.col_files")])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        lay.addWidget(self.tree, 1)

        # -------------------------------------------------------- actions
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.reanalyze_btn = QPushButton(t("btn.refresh"))
        self.reanalyze_btn.clicked.connect(self.host.controller.analyze)
        self.go_clean_btn = QPushButton(t("results.btn_go_clean"))
        self.go_clean_btn.clicked.connect(lambda: self.host.navigate("clean"))
        actions.addWidget(self.reanalyze_btn)
        actions.addWidget(self.go_clean_btn)
        lay.addLayout(actions)

    # ------------------------------------------------------------ events

    def refresh(self) -> None:
        """Repopulate the table from the controller (no disk access)."""
        self._refresh_table()

    def on_show(self) -> None:
        self._refresh_table()

    def on_clean_finished(self, summary: CleanSummary) -> None:
        """Show the final outcome and the post-clean results (accurate
        without re-scanning: sizes were updated during deletion)."""
        self._last_summary = summary
        self.summary_lbl.setText(
            t("results.summary",
              freed=format_size(summary.freed),
              removed=f"{summary.removed:,}",
              errors=f"{summary.errors:,}"))
        self.summary_lbl.setObjectName(
            "errorText" if summary.errors else "successText")
        self.summary_lbl.show()
        self._refresh_table()

    def on_clean_cancelled(self) -> None:
        self.summary_lbl.setObjectName("errorText")
        self.summary_lbl.setText(t("status.clean_cancelled"))
        self.summary_lbl.show()

    def _refresh_table(self) -> None:
        self.tree.clear()
        for r in self.host.controller.get_results():
            item = QTreeWidgetItem([
                f"{r.icon}  {r.label}",
                format_size(r.size) if r.size else "-",
                f"{r.files:,}" if r.files else "-",
            ])
            item.setToolTip(0, r.description)
            self.tree.addTopLevelItem(item)
        if self._last_summary is None and self.tree.topLevelItemCount() == 0:
            self.summary_lbl.setText(t("results.empty"))
            self.summary_lbl.setObjectName("cardDesc")
            self.summary_lbl.show()

    def on_busy(self, busy: bool) -> None:
        self.reanalyze_btn.setEnabled(not busy)
