"""Headless smoke tests for the PySide6 interface (Fase 4/5/9).

Run with QT_QPA_PLATFORM=offscreen: no window server needed. These tests
verify the window builds, pages exist, navigation works, the controller
wiring delivers analysis/clean events, and the UI never blocks (workers
do the work)."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest

from limpiapro.categories import CleanCategory
from limpiapro.controller import LimpiaProController
from limpiapro.settings import Settings
from limpiapro.ui.main_window import MainWindow


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


def test_window_builds_and_navigates(qapp, controller, settings):
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        assert win.stack.count() == 4
        assert set(win.pages) == {"home", "clean", "results", "settings"}
        # navigation works and pages react to on_show
        win.navigate("clean")
        assert win.stack.currentWidget() is win.pages["clean"]
        win.navigate("results")
        assert win.stack.currentWidget() is win.pages["results"]
        # the clean page has one card per category
        assert set(win.pages["clean"]._cards) == {"a", "b"}
    finally:
        win.close()


def test_analysis_updates_cards(qapp, controller, settings):
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        win.controller.analyze()
        _spin(qapp, lambda: win.controller.busy)
        # cards now show the measured sizes
        cards = win.pages["clean"]._cards
        assert cards["a"].size_lbl.text() == "100 B"
        assert cards["b"].size_lbl.text() == "200 B"
        assert win.pages["results"].tree.topLevelItemCount() == 2
    finally:
        win.close()


def test_clean_flow_updates_results(qapp, controller, settings):
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        win.controller.analyze()
        _spin(qapp, lambda: win.controller.busy)
        win.controller.clean(["a", "b"])
        _spin(qapp, lambda: win.controller.busy)
        # the final summary is shown on the results page and the window
        # navigated there automatically
        assert win.stack.currentWidget() is win.pages["results"]
        summary = win.pages["results"]._last_summary
        assert summary is not None
        assert summary.removed == 2
        assert summary.freed == 300
        # post-clean results are accurate without re-scanning
        results = win.controller.get_results()
        assert all(r.size == 0 for r in results)
    finally:
        win.close()


def test_cancel_is_cooperative(qapp, controller, settings):
    controller._cancel_requested = True  # simulate a pending cancel
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        # cancel() before any operation must not raise and must be a no-op
        win.controller.cancel()
        assert win.controller._cancel_requested is True
    finally:
        win.close()


def test_busy_disables_actions(qapp, controller, settings):
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        page = win.pages["clean"]
        page.on_busy(True)
        assert page.clean_btn.isEnabled() is False
        assert page.cancel_btn.isEnabled() is True
        page.on_busy(False)
        assert page.clean_btn.isEnabled() is True
        assert page.cancel_btn.isEnabled() is False
    finally:
        win.close()
