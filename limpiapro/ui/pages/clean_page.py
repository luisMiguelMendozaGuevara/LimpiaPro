"""Page: Limpieza (category selection, preview, clean)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...controller import CategoryResult
from ...i18n import t
from ...utils import format_size
from ..dialogs import ConfirmCleanDialog, PreviewDialog
from ..widgets import CategoryCard


class CleanPage(QWidget):
    """The main cleaning page: one card per category, total and actions.

    It drives the flow Analizar -> Resultados (preview/snapshot) ->
    Confirmar -> (SafetyGuard inside the core) -> Eliminar -> Resultado."""

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        self._cards: dict[str, CategoryCard] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        title = QLabel(t("clean.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("clean.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        # ------------------------------------------------------- toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.all_btn = QPushButton(t("btn.select_all"))
        self.all_btn.clicked.connect(lambda: self.toggle_all(True))
        self.none_btn = QPushButton(t("btn.none"))
        self.none_btn.clicked.connect(lambda: self.toggle_all(False))
        self.analyze_btn = QPushButton(t("btn.refresh"))
        self.analyze_btn.clicked.connect(self.host.controller.analyze)
        self.winapp_btn = QPushButton(t("btn.winapp_rules"))
        self.winapp_btn.clicked.connect(self._load_winapp)
        self.preview_btn = QPushButton(t("btn.preview"))
        self.preview_btn.clicked.connect(self._preview)
        self.cancel_btn = QPushButton(t("btn.cancel"))
        self.cancel_btn.clicked.connect(self.host.controller.cancel)
        self.clean_btn = QPushButton(t("btn.clean_selected"))
        self.clean_btn.setProperty("kind", "primary")
        self.clean_btn.clicked.connect(self._confirm_and_clean)
        for b in (self.all_btn, self.none_btn, self.analyze_btn,
                  self.winapp_btn, self.preview_btn, self.cancel_btn):
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        toolbar.addWidget(self.clean_btn)
        lay.addLayout(toolbar)

        # ------------------------------------------------------ card list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._list_host = QWidget()
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 6, 0)
        self._list_lay.setSpacing(8)
        self._list_lay.addStretch(1)
        scroll.setWidget(self._list_host)
        lay.addWidget(scroll, 1)

        # ---------------------------------------------------------- footer
        footer = QHBoxLayout()
        self.total_lbl = QLabel(t("clean.total_calculating"))
        self.total_lbl.setObjectName("cardTitle")
        footer.addWidget(self.total_lbl)
        footer.addStretch(1)
        self.status_lbl = QLabel(t("status.ready"))
        self.status_lbl.setObjectName("statusText")
        footer.addWidget(self.status_lbl)
        lay.addLayout(footer)

        self._build_cards()
        self.on_busy(False)

    # ----------------------------------------------------------- helpers

    def _build_cards(self) -> None:
        """(Re)build one card per category from the current results."""
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cards = {}
        for result in self.host.controller.get_results():
            card = CategoryCard(result)
            card.toggled.connect(lambda _k, _on: self.update_total())
            self._list_lay.insertWidget(self._list_lay.count() - 1, card)
            self._cards[result.key] = card

    def toggle_all(self, value: bool) -> None:
        for card in self._cards.values():
            card.set_checked(value)
        self.update_total()

    def selected(self) -> list[CategoryResult]:
        """The checked categories as result rows."""
        by_key = {r.key: r for r in self.host.controller.get_results()}
        return [by_key[k] for k, card in self._cards.items()
                if card.is_checked() and k in by_key]

    def update_total(self) -> None:
        total = sum(r.size for r in self.selected())
        self.total_lbl.setText(t("clean.total", size=format_size(total)))

    def on_category_updated(self, key: str) -> None:
        card = self._cards.get(key)
        if card is None:
            return
        by_key = {r.key: r for r in self.host.controller.get_results()}
        result = by_key.get(key)
        if result is not None:
            card.set_result(result)
        self.update_total()

    # ------------------------------------------------------------ actions

    def _load_winapp(self) -> None:
        path, _f = QFileDialog.getOpenFileName(
            self, t("dialog.winapp_title"), "",
            f"{t('dialog.winapp_filter')} (*.ini);;{t('dialog.all_files')} (*.*)")
        if path:
            self.host.controller.load_winapp_rules(path)

    def _preview(self) -> None:
        selected = self.selected()
        if not selected:
            self._flash_status(t("msg.no_categories"))
            return
        self.host.preview_flow([r.key for r in selected])

    def on_preview_done(self, data) -> None:
        """Show the collected preview in a dialog (already off the UI
        thread; the snapshot for the upcoming clean was taken too)."""
        dlg = PreviewDialog(data, self)
        dlg.exec()

    def on_preview_error(self, message: str) -> None:
        self._flash_status(f"{t('msg.preview_error', exc=message)}")

    def _confirm_and_clean(self) -> None:
        selected = self.selected()
        if not selected:
            self._flash_status(t("msg.no_categories"))
            return
        if self.host.settings.confirm_before_clean:
            total = sum(r.size for r in selected)
            needs_admin = any(r.needs_admin for r in selected)
            includes_recycle = any(r.recycle_bin for r in selected)
            dlg = ConfirmCleanDialog(selected, total, needs_admin,
                                     includes_recycle, self)
            if not dlg.exec():
                return
        self.host.controller.clean([r.key for r in selected])

    # ------------------------------------------------------------- state

    def on_busy(self, busy: bool) -> None:
        """Disable everything except Cancel while an operation runs."""
        for b in (self.all_btn, self.none_btn, self.analyze_btn,
                  self.winapp_btn, self.preview_btn, self.clean_btn):
            b.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)

    def _flash_status(self, text: str) -> None:
        self.status_lbl.setText(text)

    def on_show(self) -> None:
        self.update_total()

    def set_status(self, text: str) -> None:
        self.status_lbl.setText(text)
