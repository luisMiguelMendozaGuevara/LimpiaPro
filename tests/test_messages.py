"""Tests for the dialog message presenters (ui.messages)."""

from limpiapro.i18n import t
from limpiapro.ui.messages import clean_confirmation


class _Cat:
    def __init__(self, key, label, size, recycle=False, needs_admin=False):
        self.key = key
        self.label = label
        self.size = size
        self.recycle_bin = recycle
        self.needs_admin = needs_admin


def test_clean_confirmation_builds_heading_and_items():
    # Language-agnostic: CI runs in English, development in Spanish, and
    # both must pass. Sizes come from format_size (locale-independent).
    heading, _subtitle, items, notes = clean_confirmation(
        [_Cat("browser", "Cache de navegadores", 1_500_000_000),
         _Cat("temp", "Archivos temporales", 500_000)])
    assert "2" in heading
    assert "1.4 GB" in heading
    assert items[0] == ("Cache de navegadores", "1.4 GB")
    assert items[1][1] == "488.3 KB"
    assert t("msg.clean_note_browsers") in notes


def test_clean_confirmation_adds_recycle_note():
    _h, _s, _i, notes = clean_confirmation(
        [_Cat("recycle", "Papelera", 0, recycle=True)])
    assert t("msg.clean_note_recycle") in notes


def test_clean_confirmation_adds_winapp_note():
    _h, _s, _i, notes = clean_confirmation(
        [_Cat("winapp", "Aplicaciones (reglas winapp2)", 12_000)])
    assert t("msg.clean_note_winapp") in notes


def test_clean_confirmation_empty_size_shows_clean():
    _h, _s, items, _n = clean_confirmation(
        [_Cat("history", "Historial", 0)])
    assert items[0][1] == t("clean.is_clean")


def test_clean_confirmation_heading_uses_formatted_size():
    heading, _s, _i, _n = clean_confirmation(
        [_Cat("temp", "Temp", 3_000_000_000)])
    assert "2.8 GB" in heading


def test_clean_confirmation_subtitle_is_static():
    _h, subtitle, _i, _n = clean_confirmation([_Cat("temp", "Temp", 1)])
    assert subtitle == t("msg.clean_confirm_sub")
