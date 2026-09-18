"""Page: settings (theme, language, behavior, data locations).

Every change is applied and persisted immediately (the app autosaves), and
the language note makes clear when a restart is needed.
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME, APP_VERSION
from ...i18n import set_language, t
from ...paths import get_cache_file, get_logs_dir, get_user_data_dir
from .. import icons

# Settings value -> i18n key for the theme selector.
_THEMES = (("dark", "settings.theme_dark"),
           ("light", "settings.theme_light"),
           ("system", "settings.theme_system"))

# Settings value -> i18n key for the language selector.
_LANGS = (("auto", "settings.lang_auto"),
          ("es", "settings.lang_es"),
          ("en", "settings.lang_en"))


class SettingsPage(QWidget):
    """Preferences: appearance, language, behavior and data locations."""

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host
        self._icon_refs: list[tuple[QPushButton, str]] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(8)

        title = QLabel(t("settings.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("settings.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        lay.addWidget(self._appearance_card())
        lay.addWidget(self._language_card())
        lay.addWidget(self._behavior_card())
        lay.addWidget(self._locations_card())

        about = QLabel(f"{APP_NAME} {APP_VERSION}")
        about.setObjectName("mutedText")
        lay.addWidget(about)
        lay.addStretch(1)

    # ------------------------------------------------------------- cards

    def _card(self, heading_key: str) -> tuple[QFrame, QVBoxLayout]:
        """A titled settings card (same surface as the category rows)."""
        card = QFrame()
        card.setObjectName("settingCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(8)
        heading = QLabel(t(heading_key))
        heading.setObjectName("sectionTitle")
        box.addWidget(heading)
        return card, box

    @staticmethod
    def _row(label_key: str, control: QWidget) -> QWidget:
        """One 'label .......... control' row."""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        label = QLabel(t(label_key))
        lay.addWidget(label)
        lay.addStretch(1)
        lay.addWidget(control)
        return row

    def _appearance_card(self) -> QFrame:
        card, box = self._card("settings.group_appearance")
        self.theme_combo = QComboBox()
        for value, key in _THEMES:
            self.theme_combo.addItem(t(key), value)
        self._select_value(self.theme_combo, self.host.settings.theme)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        box.addWidget(self._row("settings.theme", self.theme_combo))
        return card

    def _language_card(self) -> QFrame:
        card, box = self._card("settings.language")
        self.lang_combo = QComboBox()
        for value, key in _LANGS:
            self.lang_combo.addItem(t(key), value)
        self._select_value(self.lang_combo, self.host.settings.language)
        self.lang_combo.currentIndexChanged.connect(self._on_language_changed)
        box.addWidget(self._row("settings.language", self.lang_combo))
        note = QLabel(t("settings.lang_note"))
        note.setObjectName("catDesc")
        note.setWordWrap(True)
        box.addWidget(note)
        return card

    def _behavior_card(self) -> QFrame:
        from PySide6.QtWidgets import QCheckBox

        card, box = self._card("settings.group_behaviors")
        self.auto_analyze_chk = QCheckBox(t("settings.auto_analyze"))
        self.auto_analyze_chk.setChecked(bool(self.host.settings.auto_analyze))
        self.auto_analyze_chk.toggled.connect(
            lambda on: self._save("auto_analyze", bool(on)))
        self.confirm_chk = QCheckBox(t("settings.confirm_clean"))
        self.confirm_chk.setChecked(bool(self.host.settings.confirm_before_clean))
        self.confirm_chk.toggled.connect(
            lambda on: self._save("confirm_before_clean", bool(on)))
        self.recycle_chk = QCheckBox(t("settings.recycle_bin"))
        self.recycle_chk.setChecked(bool(self.host.settings.delete_to_recycle_bin))
        self.recycle_chk.toggled.connect(self._on_recycle_changed)
        for chk in (self.auto_analyze_chk, self.confirm_chk,
                    self.recycle_chk):
            box.addWidget(chk)
        return card

    def _locations_card(self) -> QFrame:
        card, box = self._card("settings.group_paths")
        for label_key, path in (
                ("settings.data_dir", get_user_data_dir()),
                ("settings.logs", get_logs_dir()),
                ("settings.cache", get_cache_file())):
            btn = QPushButton(t(label_key))
            self._icon_refs.append((btn, "folder"))
            btn.clicked.connect(
                lambda _=False, p=path: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(p)))
            box.addWidget(btn)
        self.refresh_icons()
        return card

    # ----------------------------------------------------------- helpers

    @staticmethod
    def _select_value(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def _save(self, attribute: str, value) -> None:
        setattr(self.host.settings, attribute, value)
        self.host.settings.save()
        self.host.set_status(t("settings.saved"))

    def _on_theme_changed(self, index: int) -> None:
        theme = self.theme_combo.itemData(index)
        if not theme or theme == self.host.settings.theme:
            return
        self.host.settings.theme = theme
        self.host.settings.save()
        self.host.apply_theme()
        self.host.set_status(t("settings.saved"))

    def _on_language_changed(self, index: int) -> None:
        code = self.lang_combo.itemData(index)
        if not code or code == self.host.settings.language:
            return
        self.host.settings.language = code
        self.host.settings.save()
        # "auto" applies the detected system language; the visible text
        # switches on the next start (already-built widgets keep theirs).
        set_language(code)
        self.host.set_status(t("settings.saved"))

    def _on_recycle_changed(self, on: bool) -> None:
        self.host._on_recycle_toggled(on)
        self.host.set_status(t("settings.saved"))

    def refresh_icons(self) -> None:
        """Re-apply the button icons after a dark/light switch."""
        for btn, name in self._icon_refs:
            icons.apply(btn, name)

    def refresh_from_settings(self) -> None:
        """Re-read the widgets from the settings object (e.g. after the
        sidebar theme toggle changed the theme)."""
        self._select_value(self.theme_combo, self.host.settings.theme)
        self._select_value(self.lang_combo, self.host.settings.language)
        for chk, attr in ((self.auto_analyze_chk, "auto_analyze"),
                          (self.confirm_chk, "confirm_before_clean"),
                          (self.recycle_chk, "delete_to_recycle_bin")):
            chk.blockSignals(True)
            chk.setChecked(bool(getattr(self.host.settings, attr)))
            chk.blockSignals(False)

    def on_busy(self, busy: bool) -> None:
        """Settings stay usable while a scan runs: nothing to disable."""

    def on_show(self) -> None:
        self.refresh_from_settings()
