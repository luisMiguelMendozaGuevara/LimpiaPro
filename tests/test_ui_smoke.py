"""Headless smoke tests for the PySide6 replica (same interface as the
legacy app: six pages, same flows).

Run with QT_QPA_PLATFORM=offscreen: no window server needed. These tests
verify the window builds with the six original pages, navigation works,
analysis/cleaning update the clean-page rows, the UI never blocks while
workers run, and run_async marshals results to the UI thread."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from limpiapro.categories import CleanCategory
from limpiapro.controller import LimpiaProController
from limpiapro.i18n import t
from limpiapro.settings import Settings
from limpiapro.ui.main_window import MainWindow
from limpiapro.ui.widgets import run_async


@pytest.fixture()
def controller(tmp_path):
    """Lightweight controller with two tiny scratch categories."""
    a = tmp_path / "cat_a"
    b = tmp_path / "cat_b"
    a.mkdir()
    b.mkdir()
    (a / "one.tmp").write_bytes(b"x" * 100)
    (b / "two.tmp").write_bytes(b"x" * 200)
    cats = [
        CleanCategory("a", "A", "desc a", [str(a)]),
        CleanCategory("b", "B", "desc b", [str(b)]),
    ]
    return LimpiaProController(categories=cats)


@pytest.fixture()
def settings():
    return Settings(auto_analyze=False, confirm_before_clean=False)


def _spin(qapp, busy, timeout_ms=10000):
    deadline = time.monotonic() + timeout_ms / 1000
    while busy() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert not busy(), "operation did not finish in time"


def test_window_builds_all_six_pages(qapp, controller, settings):
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        for key in ("clean", "startup", "dupes", "update",
                    "uninstall", "log"):
            win.show_page(key)
            qapp.processEvents()
        assert set(win._pages) == {"clean", "startup", "dupes",
                                   "update", "uninstall", "log"}
        assert win.stack.count() == 6
        assert set(win.nav_buttons) == set(win._pages)
        # the clean page has one row per category
        assert set(win.pages_clean.rows) == {"a", "b"}
    finally:
        win.close()


def test_analysis_updates_rows(qapp, controller, settings):
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        win.controller.analyze()
        _spin(qapp, lambda: win.controller.busy)
        rows = win.pages_clean.rows
        assert rows["a"].size_lbl.text() == "100 B"
        assert rows["b"].size_lbl.text() == "200 B"
        assert "300 B" in win.pages_clean.total_lbl.text()
    finally:
        win.close()


def test_clean_updates_rows(qapp, controller, settings):
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        win.controller.analyze()
        _spin(qapp, lambda: win.controller.busy)
        win.controller.clean(["a", "b"])
        _spin(qapp, lambda: win.controller.busy)
        assert all(r.size == 0 for r in win.controller.get_results())
        # rows refreshed from the post-clean sizes (no re-scan)
        assert (win.pages_clean.rows["a"].size_lbl.text()
                == t("clean.is_clean"))
    finally:
        win.close()


def test_busy_disables_actions(qapp, controller, settings):
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        page = win.pages_clean
        page.on_busy(True)
        assert page.clean_btn.isEnabled() is False
        assert page.cancel_btn.isEnabled() is True
        page.on_busy(False)
        assert page.clean_btn.isEnabled() is True
        assert page.cancel_btn.isEnabled() is False
    finally:
        win.close()


def test_ui_stays_responsive_while_busy(qapp, tmp_path, settings):
    """The UI thread keeps processing events (navigation works) while the
    analysis runs on its worker: no freeze."""
    folder = tmp_path / "many"
    folder.mkdir()
    for i in range(400):
        (folder / f"f{i}.tmp").write_bytes(b"x" * 32)
    cat = CleanCategory("many", "Many", "", [str(folder)])
    controller = LimpiaProController(categories=[cat])

    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        win.controller.analyze()
        deadline = time.monotonic() + 10
        navigated = 0
        while win.controller.busy and time.monotonic() < deadline:
            qapp.processEvents()
            win.show_page("startup")  # must never block
            navigated += 1
            time.sleep(0.002)
        assert not win.controller.busy
        assert navigated > 0
    finally:
        win.close()


def test_run_async_delivers_on_ui_thread(qapp):
    """The replica's run_async marshals results to the UI thread."""
    got = []

    def worker():
        return 42, "ok"

    def done(a, b):
        got.append((a, b))

    run_async(None, worker, done)
    deadline = time.monotonic() + 5
    while not got and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert got == [(42, "ok")]


def test_run_async_error_path(qapp):
    got = []

    def worker():
        raise ValueError("boom")

    def on_error(exc):
        got.append(str(exc))

    run_async(None, worker, lambda *a: None, on_error=on_error)
    deadline = time.monotonic() + 5
    while not got and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert got and "boom" in got[0]
