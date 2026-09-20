"""Page: system cleanup 

Shows one row per cleaning category with a checkbox, the measured size
and the file count. The bottom bar holds the selected total, the global
progress bar and the status label used by the whole app."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...i18n import t
from ...utils import format_size
from .. import icons
from ..layouts import FlowLayout


class CategoryRow(QWidget):
    """One category row: checkbox + icon + labels + size/count."""

    toggled = Signal(str, bool)  # (category key, checked)

    def __init__(self, cat, checked: bool = True,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.key = cat.key
        self.setObjectName("catRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)

        self.check = QCheckBox()
        self.check.setChecked(checked)
        self.check.toggled.connect(lambda on, k=cat.key: self.toggled.emit(k, on))
        lay.addWidget(self.check, 0, Qt.AlignTop)

        # Themed SVG icon instead of the legacy emoji glyph.
        self._icon_name = icons.CATEGORY_ICONS.get(cat.key, "file")
        self.icon_lbl = QLabel()
        self.icon_lbl.setPixmap(icons.pixmap(self._icon_name,
                                             icons._ICON_SIZE, role="muted"))
        self.icon_lbl.setFixedSize(icons._ICON_SIZE + 4,
                                   icons._ICON_SIZE + 4)
        self.icon_lbl.setAlignment(Qt.AlignTop)
        lay.addWidget(self.icon_lbl, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.title_lbl = QLabel(cat.label)
        self.title_lbl.setObjectName("catTitle")
        admin = t("clean.needs_admin") if cat.needs_admin else ""
        self.desc_lbl = QLabel(cat.description + admin)
        self.desc_lbl.setObjectName("catDesc")
        self.desc_lbl.setWordWrap(True)
        text_col.addWidget(self.title_lbl)
        text_col.addWidget(self.desc_lbl)
        lay.addLayout(text_col, 1)

        right = QVBoxLayout()
        right.setSpacing(0)
        self.size_lbl = QLabel()
        self.size_lbl.setObjectName("catSize")
        self.size_lbl.setAlignment(Qt.AlignRight)
        self.count_lbl = QLabel()
        self.count_lbl.setObjectName("catCount")
        self.count_lbl.setAlignment(Qt.AlignRight)
        right.addWidget(self.size_lbl)
        right.addWidget(self.count_lbl)
        lay.addLayout(right, 0)

        self.set_result(cat)

    # ------------------------------------------------------------ state

    def is_checked(self) -> bool:
        return self.check.isChecked()

    def set_checked(self, value: bool) -> None:
        self.check.setChecked(value)

    def set_result(self, cat) -> None:
        """Refresh the displayed size/count from a category object."""
        if cat.recycle_bin:
            txt = f"~{format_size(cat.size)}" if cat.size else t("clean.recycle_empty")
            count = ""
        else:
            txt = format_size(cat.size) if cat.size else t("clean.is_clean")
            count = t("clean.n_files", n=f"{cat.files:,}") if cat.files else ""
        self.size_lbl.setText(txt)
        self.count_lbl.setText(count)


class CleanPage(QWidget):
    """Main cleanup page: category checkboxes plus totals and progress."""

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        self.rows: dict[str, CategoryRow] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(8)

        title = QLabel(t("clean.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("clean.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        # ------------------------------------------------------- toolbar
        # Two visual groups, the conventional desktop layout:
        #   row 1: tools (wraps on narrow windows via FlowLayout)
        #   row 2: primary actions, right-aligned (Cancelar / Limpiar)
        # The recycle-bin preference moved to the Settings page.
        tools = FlowLayout(spacing=8)
        # Single smart toggle: shows the action it will perform
        # ("Seleccionar todo" / "Deseleccionar todo").
        self.all_btn = QPushButton(t("btn.select_all"))
        self.all_btn.clicked.connect(self._toggle_selection)
        self.preview_btn = QPushButton(t("btn.preview"))
        self.preview_btn.clicked.connect(self.host.preview_clean)
        self.winapp_btn = QPushButton(t("btn.winapp_rules"))
        self.winapp_btn.clicked.connect(self.host.load_winapp_rules)
        self.analyze_btn = QPushButton(t("btn.analyze"))
        self.analyze_btn.clicked.connect(self.host.analyze_all)
        for b in (self.all_btn, self.preview_btn, self.winapp_btn,
                  self.analyze_btn):
            tools.addWidget(b)
        lay.addLayout(tools)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        self.cancel_btn = QPushButton(t("btn.cancel"))
        self.cancel_btn.clicked.connect(self.host.request_cancel)
        self.clean_btn = QPushButton(t("btn.clean_selected"))
        self.clean_btn.setProperty("kind", "primary")
        self.clean_btn.clicked.connect(self.host.confirm_clean)
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.clean_btn)
        lay.addLayout(actions)
        self._apply_button_icons()

        # ------------------------------------------------------ card list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._list_host = QWidget()
        self._list_lay = QVBoxLayout(self._list_host)
        self._list_lay.setContentsMargins(0, 0, 6, 0)
        self._list_lay.setSpacing(6)
        self._list_lay.addStretch(1)
        scroll.setWidget(self._list_host)
        lay.addWidget(scroll, 1)

        # ---------------------------------------------------------- footer
        footer = QHBoxLayout()
        footer.setSpacing(12)
        self.total_lbl = QLabel(t("clean.total_calculating"))
        self.total_lbl.setObjectName("totalText")
        footer.addWidget(self.total_lbl)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        footer.addWidget(self.progress, 1)
        self.status_lbl = QLabel(t("status.ready"))
        self.status_lbl.setObjectName("statusText")
        footer.addWidget(self.status_lbl)
        lay.addLayout(footer)

        self._build_rows()
        self.on_busy(False)

    # ----------------------------------------------------------- helpers

    def _apply_button_icons(self) -> None:
        """Attach themed icons to the toolbar buttons."""
        self._update_toggle_button()
        icons.apply(self.preview_btn, "preview")
        icons.apply(self.winapp_btn, "package")
        icons.apply(self.analyze_btn, "refresh")
        icons.apply(self.cancel_btn, "cancel", role="error")
        # Trash can for the primary action: it deletes what is selected.
        icons.apply(self.clean_btn, "trash", role="on_accent")

    def refresh_icons(self) -> None:
        """Re-apply every icon after a dark/light theme switch."""
        self._apply_button_icons()
        for row in self.rows.values():
            row.icon_lbl.setPixmap(
                icons.pixmap(row._icon_name, icons._ICON_SIZE, role="muted"))

    def _build_rows(self) -> None:
        """(Re)build one row per category from host.categories."""
        while self._list_lay.count() > 1:
            item = self._list_lay.takeAt(0)
            if item is None:
                break
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self.rows = {}
        for cat in self.host.categories:
            row = CategoryRow(cat)
            row.toggled.connect(lambda _k, _on: self.update_total())
            self._list_lay.insertWidget(self._list_lay.count() - 1, row)
            self.rows[cat.key] = row

    def _all_selected(self) -> bool:
        """True when every category row is checked."""
        return bool(self.rows) and all(r.is_checked()
                                       for r in self.rows.values())

    def _toggle_selection(self) -> None:
        """Select everything, or clear everything when all is selected."""
        self.toggle_all(not self._all_selected())

    def _update_toggle_button(self) -> None:
        """Sync the smart toggle's label and icon with the current state."""
        if not hasattr(self, "all_btn"):
            return
        if self._all_selected():
            self.all_btn.setText(t("btn.select_none"))
            icons.apply(self.all_btn, "select_none")
        else:
            self.all_btn.setText(t("btn.select_all"))
            icons.apply(self.all_btn, "select_all")

    def toggle_all(self, value: bool) -> None:
        for row in self.rows.values():
            row.set_checked(value)
        self.update_total()

    def selected_categories(self):
        """The checked category objects."""
        by_key = {c.key: c for c in self.host.categories}
        return [by_key[k] for k, row in self.rows.items()
                if row.is_checked() and k in by_key]

    def update_total(self) -> None:
        total = sum(c.size for c in self.selected_categories())
        self.total_lbl.setText(t("clean.total", size=format_size(total)))
        self._update_toggle_button()

    def on_category_updated(self, key: str) -> None:
        """Refresh one category's row as soon as its scan finishes."""
        row = self.rows.get(key)
        if row is None:
            return
        by_key = {c.key: c for c in self.host.categories}
        cat = by_key.get(key)
        if cat is not None:
            row.set_result(cat)
        self.update_total()

    def refresh_results(self) -> None:
        """Re-read every row from the category objects.

        Needed after the sizes are applied from the on-disk cache (the
        instant-startup path never emits category_updated, so the rows kept
        showing their placeholder text while the objects already had the
        real sizes).
        """
        by_key = {c.key: c for c in self.host.categories}
        for key, row in self.rows.items():
            cat = by_key.get(key)
            if cat is not None:
                row.set_result(cat)
        self.update_total()

    def update_after_scan(self, cat) -> None:
        """Alias used by the app after each category scan."""
        self.on_category_updated(cat.key)

    # ------------------------------------------------------------- state

    def on_busy(self, busy: bool) -> None:
        """Disable everything except Cancel while an operation runs."""
        for b in (self.all_btn, self.preview_btn,
                  self.winapp_btn, self.analyze_btn, self.clean_btn):
            b.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)

    def on_show(self) -> None:
        self.update_total()
