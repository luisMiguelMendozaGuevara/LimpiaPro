"""UI details: foreground on open, startup analysis, action icons."""

import time

from limpiapro import APP_VERSION
from limpiapro.controller import CACHE_SCHEMA, LimpiaProController
from limpiapro.services import CacheService
from limpiapro.settings import Settings
from limpiapro.ui import icons
from limpiapro.ui.main_window import MainWindow


def _controller(tmp_path):
    return LimpiaProController(
        cache_service=CacheService(str(tmp_path / "c.json"), CACHE_SCHEMA,
                                   APP_VERSION))


def test_window_is_surfaced_on_open(qapp, tmp_path):
    """The window must be visible and active after the startup sequence:
    an elevated process used to open behind everything."""
    from limpiapro.app_qt import _force_foreground

    win = MainWindow(settings=Settings(auto_analyze=False),
                     controller=_controller(tmp_path))
    win.show()
    _force_foreground(win)
    qapp.processEvents()
    try:
        assert win.isVisible()
        assert not win.isMinimized()
    finally:
        win.close()


def test_clean_button_uses_the_trash_icon(qapp, tmp_path):
    """The primary action deletes the selection: a trash can, not the
    sparkles used for the brand/clean identity."""
    win = MainWindow(settings=Settings(auto_analyze=False),
                     controller=_controller(tmp_path))
    try:
        button_icon = win.pages_clean.clean_btn.icon()
        assert not button_icon.isNull()
        expected = icons.icon("trash", role="on_accent").pixmap(32, 32) \
            .toImage()
        actual = button_icon.pixmap(32, 32).toImage()
        assert actual == expected, "clean button does not use the trash icon"
    finally:
        win.close()


def test_startup_analysis_runs_with_a_stale_cache(qapp, tmp_path):
    """Opening the app starts the scan on its own (no button press): the
    startup timer runs it right after the window paints."""
    from limpiapro.categories import CleanCategory

    folder = tmp_path / "cache_dir"
    folder.mkdir()
    (folder / "a.tmp").write_bytes(b"x" * 128)
    cats = [CleanCategory("a", "A", "d", [str(folder)])]

    win = MainWindow(settings=Settings(auto_analyze=True),
                     controller=_controller(tmp_path))
    win.controller.categories[:] = cats
    win.show()
    qapp.processEvents()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            qapp.processEvents()
            if cats[0].size and not win.busy:
                break
            time.sleep(0.02)
        assert cats[0].size == 128, "the app did not analyze on open"
    finally:
        win.close()
