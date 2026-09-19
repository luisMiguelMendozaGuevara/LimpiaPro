"""Regression: the instant-startup (fresh cache) path must refresh the
category rows, and a rule-based category that has no rules loaded must not
be persisted (a cached winapp=0 used to stick forever)."""

import time

from limpiapro import APP_VERSION
from limpiapro.categories import CleanCategory
from limpiapro.controller import CACHE_SCHEMA, LimpiaProController, _cache_payload
from limpiapro.services import CacheService
from limpiapro.settings import Settings
from limpiapro.ui.main_window import MainWindow


def _spin(qapp, busy, timeout_ms=10000):
    deadline = time.monotonic() + timeout_ms / 1000
    while busy() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert not busy(), "operation did not finish in time"


def _pump(qapp, ms):
    """Process events for a fixed time so QTimer.singleShot callbacks run."""
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)


def test_cache_payload_skips_unprepared_rule_categories():
    plain = CleanCategory("temp", "Temp", "d", [])
    plain.size, plain.files = 100, 2
    ruled = CleanCategory("winapp", "Winapp", "d", [])
    ruled.is_rule_based = True          # rules not loaded yet
    ruled.size, ruled.files = 0, 0
    prepared = CleanCategory("winapp2", "Winapp2", "d", [])
    prepared.is_rule_based = True
    prepared.rules = ["rule"]
    prepared.size, prepared.files = 500, 3

    payload = _cache_payload([plain, ruled, prepared])

    assert "winapp" not in payload, "an unprepared rule category was persisted"
    assert payload["temp"] == {"size": 100, "files": 2}
    assert payload["winapp2"] == {"size": 500, "files": 3}


def test_winapp_loaded_fires_after_busy_is_released(qapp, tmp_path):
    """Ordering contract: the busy flag must be cleared BEFORE the result is
    announced. The startup chain reacts to winapp_loaded by triggering the
    deferred analysis, and analyze_all() is a no-op while busy is set, so
    the reverse order silently dropped the first scan."""
    ini = tmp_path / "winapp2.ini"
    ini.write_text("[Fake]\nDetect=HKCU\\\\Software\\\\NoSuchKeyLimpiaPro\n"
                   "FileKey1=%TEMP%|*.no-such-extension\n", encoding="utf-8")

    controller = LimpiaProController(categories=[], defer_winapp=True)
    seen_busy = []
    controller.winapp_loaded.connect(lambda _count: seen_busy.append(
        controller.busy))
    controller.load_winapp_rules(str(ini))

    deadline = time.monotonic() + 30
    while not seen_busy and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert seen_busy == [False], f"busy at winapp_loaded: {seen_busy}"


def test_startup_analysis_is_not_dropped_while_winapp_loads(
        qapp, tmp_path, monkeypatch):
    """End-to-end: with a stale cache the first scan must run even though
    the deferred winapp load holds the controller busy when the analysis
    timer fires."""
    a = tmp_path / "cat_a"
    a.mkdir()
    (a / "one.tmp").write_bytes(b"x" * 100)
    cats = [CleanCategory("a", "A", "desc a", [str(a)])]

    ini = tmp_path / "winapp2.ini"
    # A section that is never detected keeps the parse instant.
    ini.write_text("[Fake]\nDetect=HKCU\\\\Software\\\\NoSuchKeyLimpiaPro\n"
                   "FileKey1=%TEMP%|*.no-such-extension\n", encoding="utf-8")
    monkeypatch.setattr("limpiapro.ui.main_window.default_winapp_file",
                        lambda: str(ini))

    cache_path = tmp_path / "stale_cache.json"
    service = CacheService(str(cache_path), CACHE_SCHEMA, APP_VERSION)
    # No cache file at all == stale enough to force a real scan.

    controller = LimpiaProController(categories=cats, cache_service=service,
                                     defer_winapp=True)
    settings = Settings(auto_analyze=True, confirm_before_clean=False,
                        theme="dark")
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            qapp.processEvents()
            if cats[0].size and not win.busy:
                break
            time.sleep(0.02)
        assert cats[0].size == 100, "the startup scan was dropped"
        assert win.pages_clean.rows["a"].size_lbl.text() == "100 B"
    finally:
        win.close()


def test_foreign_fresh_cache_does_not_skip_the_analysis(qapp, tmp_path):
    """A FRESH cache that describes other categories (e.g. one written by a
    test run into the real user profile) must not make the UI skip the scan
    and show nothing: that is exactly what happened in production."""
    a = tmp_path / "cat_a"
    a.mkdir()
    (a / "one.tmp").write_bytes(b"x" * 100)
    cats = [CleanCategory("a", "A", "desc a", [str(a)])]

    service = CacheService(str(tmp_path / "foreign.json"), CACHE_SCHEMA,
                           APP_VERSION)
    service.save({"many": {"size": 12800, "files": 400}}, "win32")
    assert service.is_fresh()

    controller = LimpiaProController(categories=cats, cache_service=service)
    settings = Settings(auto_analyze=True, confirm_before_clean=False)
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            qapp.processEvents()
            if cats[0].size and not win.busy:
                break
            time.sleep(0.02)
        assert cats[0].size == 100, "the analysis was skipped for a foreign cache"
        assert win.pages_clean.rows["a"].size_lbl.text() == "100 B"
    finally:
        win.close()


def test_fresh_cache_startup_refreshes_the_rows(qapp, tmp_path):
    """With a fresh cache the analysis is skipped: the numbers must still
    reach the category rows, not only the total label."""
    a = tmp_path / "cat_a"
    a.mkdir()
    (a / "one.tmp").write_bytes(b"x" * 100)
    cats = [CleanCategory("a", "A", "desc a", [str(a)])]

    cache_path = tmp_path / "cache.json"
    service = CacheService(str(cache_path), CACHE_SCHEMA, APP_VERSION)
    service.save({"a": {"size": 3_000_000_000, "files": 42}}, "win32")
    assert service.is_fresh()

    controller = LimpiaProController(categories=cats,
                                     cache_service=service)
    settings = Settings(auto_analyze=True, confirm_before_clean=False)
    win = MainWindow(settings=settings, controller=controller)
    win.show()
    qapp.processEvents()
    try:
        # Let the startup timers fire (winapp load + deferred analysis).
        _pump(qapp, 900)
        row = win.pages_clean.rows["a"]
        assert row.size_lbl.text() == "2.8 GB", row.size_lbl.text()
        assert "42" in row.count_lbl.text()
        assert "2.8 GB" in win.pages_clean.total_lbl.text()
    finally:
        win.close()
