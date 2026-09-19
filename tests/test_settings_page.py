"""Settings page: theme, language, recycle-bin preference and locations."""

import pytest

from limpiapro import APP_VERSION
from limpiapro.controller import CACHE_SCHEMA, LimpiaProController
from limpiapro.i18n import LANG, set_language
from limpiapro.services import CacheService
from limpiapro.settings import Settings
from limpiapro.ui.main_window import MainWindow
from limpiapro.ui.pages.settings_page import SettingsPage


@pytest.fixture()
def win(qapp, tmp_path):
    settings = Settings(auto_analyze=False, confirm_before_clean=False)
    controller = LimpiaProController(
        cache_service=CacheService(str(tmp_path / "c.json"), CACHE_SCHEMA,
                                   APP_VERSION))
    window = MainWindow(settings=settings, controller=controller)
    window.show_page("settings")
    qapp.processEvents()
    yield window
    window.close()


@pytest.fixture(autouse=True)
def _restore_language():
    original = LANG
    yield
    set_language(original)


def test_settings_page_is_in_the_navigation(win):
    assert "settings" in win.nav_buttons
    assert isinstance(win._get_page("settings"), SettingsPage)


def test_theme_selector_applies_and_persists(win, qapp):
    page = win._get_page("settings")
    index = page.theme_combo.findData("light")
    page.theme_combo.setCurrentIndex(index)
    qapp.processEvents()
    assert win.settings.theme == "light"
    # Back to dark for the rest of the session.
    page.theme_combo.setCurrentIndex(page.theme_combo.findData("dark"))
    qapp.processEvents()
    assert win.settings.theme == "dark"


def test_language_selector_updates_settings_and_i18n(win, qapp):
    page = win._get_page("settings")
    page.lang_combo.setCurrentIndex(page.lang_combo.findData("en"))
    qapp.processEvents()
    assert win.settings.language == "en"
    page.lang_combo.setCurrentIndex(page.lang_combo.findData("es"))
    qapp.processEvents()
    assert win.settings.language == "es"


def test_recycle_preference_is_exposed_in_settings(win, qapp):
    page = win._get_page("settings")
    assert page.recycle_chk.isChecked() is False
    page.recycle_chk.setChecked(True)
    qapp.processEvents()
    assert win.settings.delete_to_recycle_bin is True


def test_settings_twins_of_the_sidebar_theme_toggle(win, qapp):
    """Changing the theme from the sidebar must be reflected in the page."""
    page = win._get_page("settings")
    win.theme_toggle.setChecked(False)  # light
    qapp.processEvents()
    assert win.settings.theme == "light"
    assert page.theme_combo.currentData() == "light"


def test_saved_language_is_applied_on_startup(qapp, tmp_path):
    """Regression: set_language() was only reachable from this page, so a
    saved preference was never applied and the UI stayed in the detected
    language forever."""
    settings = Settings(auto_analyze=False, language="en")
    controller = LimpiaProController(
        cache_service=CacheService(str(tmp_path / "c.json"), CACHE_SCHEMA,
                                   APP_VERSION))
    window = MainWindow(settings=settings, controller=controller)
    try:
        assert window.nav_buttons["clean"].text() == "Cleanup"
        assert window.nav_buttons["settings"].text() == "Settings"
    finally:
        window.close()


def test_language_preference_round_trips(qapp, tmp_path):
    """The choice is persisted and honored on the next start."""
    path = tmp_path / "settings.json"
    Settings(auto_analyze=False, language="en").save(str(path))
    assert Settings.load(str(path)).language == "en"
