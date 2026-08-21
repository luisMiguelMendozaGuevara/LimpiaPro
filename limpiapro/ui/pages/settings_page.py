"""Page: Configuracion (theme, language, behaviors, paths)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME, APP_VERSION
from ...i18n import t
from ...paths import get_cache_file, get_logs_dir, get_user_data_dir


class SettingsPage(QWidget):
    """Persisted preferences (limpiapro.settings.Settings)."""

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 24)
        lay.setSpacing(14)

        title = QLabel(t("settings.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("settings.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        # ---------------------------------------------------- appearance
        appearance = QGroupBox(t("settings.group_appearance"))
        form = QFormLayout(appearance)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem(t("settings.theme_dark"), "dark")
        self.theme_combo.addItem(t("settings.theme_light"), "light")
        self.theme_combo.addItem(t("settings.theme_system"), "system")
        form.addRow(t("settings.theme"), self.theme_combo)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem(t("settings.lang_auto"), "auto")
        self.lang_combo.addItem("Español", "es")
        self.lang_combo.addItem("English", "en")
        form.addRow(t("settings.language"), self.lang_combo)
        lang_note = QLabel(t("settings.lang_note"))
        lang_note.setObjectName("cardDesc")
        form.addRow("", lang_note)
        lay.addWidget(appearance)

        # ----------------------------------------------------- behaviors
        behaviors = QGroupBox(t("settings.group_behaviors"))
        beh = QVBoxLayout(behaviors)
        self.auto_analyze_check = QCheckBox(t("settings.auto_analyze"))
        self.confirm_check = QCheckBox(t("settings.confirm_clean"))
        beh.addWidget(self.auto_analyze_check)
        beh.addWidget(self.confirm_check)
        lay.addWidget(behaviors)

        # ---------------------------------------------------------- paths
        paths = QGroupBox(t("settings.group_paths"))
        pform = QFormLayout(paths)
        for label, value in (
            (t("settings.cache"), get_cache_file()),
            (t("settings.logs"), get_logs_dir()),
            (t("settings.data_dir"), get_user_data_dir()),
        ):
            pform.addRow(label, self._path_label(value))
        lay.addWidget(paths)

        # ---------------------------------------------------------- about
        about = QGroupBox(t("settings.group_about"))
        alay = QHBoxLayout(about)
        alay.addWidget(QLabel(f"{APP_NAME} {APP_VERSION}"))
        alay.addStretch(1)
        lay.addWidget(about)

        self.saved_lbl = QLabel("")
        self.saved_lbl.setObjectName("successText")
        lay.addWidget(self.saved_lbl)
        lay.addStretch(1)

        self._load()
        # Save on every control change (wired once, after _load so the
        # initial population does not trigger saves).
        self.theme_combo.currentIndexChanged.connect(self._save)
        self.lang_combo.currentIndexChanged.connect(self._save)
        self.auto_analyze_check.toggled.connect(self._save)
        self.confirm_check.toggled.connect(self._save)

    @staticmethod
    def _path_label(value: str) -> QLabel:
        from PySide6.QtCore import Qt
        lbl = QLabel(value)
        lbl.setObjectName("cardDesc")
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return lbl

    # -------------------------------------------------------------- state

    def _load(self) -> None:
        s = self.host.settings
        self.theme_combo.setCurrentIndex(
            max(0, self.theme_combo.findData(s.theme)))
        self.lang_combo.setCurrentIndex(
            max(0, self.lang_combo.findData(s.language)))
        self.auto_analyze_check.setChecked(s.auto_analyze)
        self.confirm_check.setChecked(s.confirm_before_clean)

    def _save(self) -> None:
        s = self.host.settings
        s.theme = self.theme_combo.currentData()
        s.language = self.lang_combo.currentData()
        s.auto_analyze = self.auto_analyze_check.isChecked()
        s.confirm_before_clean = self.confirm_check.isChecked()
        s.save()
        self.host.apply_settings()
        self.saved_lbl.setText(t("settings.saved"))
        self.saved_lbl.show()

    def on_show(self) -> None:
        self.saved_lbl.hide()
