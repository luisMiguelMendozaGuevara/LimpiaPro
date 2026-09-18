"""Controller (Fase 3/5): the UI-facing API works without a QApplication
by running workers synchronously; the QThread wiring is exercised with a
QCoreApplication + event processing."""

import time
from pathlib import Path

from limpiapro.categories import CleanCategory
from limpiapro.controller import (
    AnalysisWorker,
    CategoryResult,
    CleanSummary,
    CleanWorker,
    LimpiaProController,
    PreviewWorker,
    TaskWorker,
)

REPO = Path(__file__).resolve().parent.parent


def _make_categories(tmp_path):
    """Two plain categories with real files under a scratch dir."""
    a = tmp_path / "cat_a"
    b = tmp_path / "cat_b"
    a.mkdir()
    b.mkdir()
    (a / "one.tmp").write_bytes(b"x" * 100)
    (a / "two.tmp").write_bytes(b"x" * 200)
    (b / "three.tmp").write_bytes(b"x" * 400)
    cat_a = CleanCategory("a", "A", "", [str(a)])
    cat_b = CleanCategory("b", "B", "", [str(b)])
    return [cat_a, cat_b]


def test_analysis_worker_scans_and_caches(tmp_path):
    cats = _make_categories(tmp_path)
    events = []
    worker = AnalysisWorker(cats, lambda: False)
    worker.progress.connect(lambda label, frac: events.append(("progress", label)))
    worker.category_done.connect(lambda key: events.append(("done", key)))
    worker.finished.connect(lambda: events.append(("finished", "")))

    worker.run()

    assert cats[0].size == 300 and cats[0].files == 2
    assert cats[1].size == 400 and cats[1].files == 1
    assert ("finished", "") in events
    assert ("done", "a") in events and ("done", "b") in events


def test_analysis_worker_cancels(tmp_path):
    cats = _make_categories(tmp_path)
    cancelled = []
    worker = AnalysisWorker(cats, lambda: True)  # cancel immediately
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.finished.connect(lambda: cancelled.append(False))
    worker.run()
    assert cancelled == [True]


def test_preview_worker_snapshots(tmp_path):
    cats = _make_categories(tmp_path)
    result = []
    worker = PreviewWorker(cats, limit=10)
    worker.done.connect(result.append)
    worker.run()
    key, _files, scanned = result[0][0]
    assert key == "a" and scanned == 2
    # list_files snapshotted the exact target set for the upcoming clean.
    assert cats[0]._snapshot is not None


def test_clean_worker_uses_snapshot(tmp_path):
    cats = _make_categories(tmp_path)
    # preview first (snapshot), then clean: no re-walk, exact targets.
    PreviewWorker(cats, limit=10).run()
    summary = []
    worker = CleanWorker(cats, lambda: False)
    worker.finished.connect(summary.append)
    worker.run()
    assert len(summary) == 1
    s: CleanSummary = summary[0]
    assert s.removed == 3
    assert s.errors == 0
    assert s.freed == 700
    assert not (tmp_path / "cat_a" / "one.tmp").exists()
    # Category sizes were updated in place: get_results is accurate
    # without re-scanning.
    assert cats[0].size == 0


def test_clean_worker_cancels_between_categories(tmp_path):
    cats = _make_categories(tmp_path)
    state = {"calls": 0}

    def should_cancel():
        state["calls"] += 1
        return state["calls"] > 1  # cancel after the first category

    cancelled = []
    worker = CleanWorker(cats, should_cancel)
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.finished.connect(lambda: cancelled.append(False))
    worker.run()
    assert cancelled == [True]


def test_task_worker_done_and_failed():
    ok = []
    worker = TaskWorker(lambda: 42)
    worker.done.connect(ok.append)
    worker.run()
    assert ok == [42]

    errs = []

    def boom():
        raise ValueError("boom")
    bad = TaskWorker(boom)
    bad.failed.connect(errs.append)
    bad.run()
    assert errs and "boom" in errs[0]


def test_controller_api_roundtrip(tmp_path, qapp):
    """Controller analyze -> preview -> clean -> get_results, exercising
    the QThread wiring through a QApplication event loop."""
    cats = _make_categories(tmp_path)
    controller = LimpiaProController(categories=cats)
    seen = {"analyzed": [0], "previewed": [0], "cleaned": [0]}

    controller.analysis_finished.connect(
        lambda: seen["analyzed"].__setitem__(0, seen["analyzed"][0] + 1))
    controller.preview_done.connect(
        lambda data: seen["previewed"].__setitem__(0, seen["previewed"][0] + 1))
    controller.clean_finished.connect(
        lambda s: seen["cleaned"].__setitem__(0, seen["cleaned"][0] + 1))

    controller.analyze()
    _spin(qapp, lambda: controller.busy)
    controller.preview(["a", "b"])
    _spin(qapp, lambda: controller.busy)
    controller.clean(["a", "b"])
    _spin(qapp, lambda: controller.busy)

    assert seen["analyzed"][0] == 1
    assert seen["previewed"][0] == 1
    assert seen["cleaned"][0] == 1
    results = controller.get_results()
    assert isinstance(results, list) and len(results) == 2
    assert all(isinstance(r, CategoryResult) for r in results)
    assert all(r.size == 0 for r in results)


def _spin(app, busy_flag, timeout_ms=10000):
    """Process events until the controller is no longer busy."""
    deadline = time.monotonic() + timeout_ms / 1000
    while busy_flag() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert not busy_flag(), "operation did not finish in time"


def test_controller_rejects_double_operation(tmp_path):
    cats = _make_categories(tmp_path)
    controller = LimpiaProController(categories=cats)
    # Simulate an in-flight operation: busy without a thread.
    controller._set_busy(True)
    controller.analyze()  # must be a no-op
    controller.clean(["a"])
    controller.preview(["a"])


def test_load_winapp_rules_delivers_the_count(qapp):
    """Regression: TaskWorker.done emits PyObject, and PySide6 raises
    'Failed to connect signal "done(PyObject)" to "winapp_loaded(int)"'
    at connect time, which broke the whole winapp-rules load. The signal
    must stay Signal(object) and still deliver the detected rule count."""
    ini = REPO / "winapp2.ini"
    if not ini.exists():
        import pytest
        pytest.skip("bundled winapp2.ini not present")

    controller = LimpiaProController()
    seen = []
    controller.winapp_loaded.connect(seen.append)
    controller.winapp_error.connect(
        lambda msg: seen.append(RuntimeError(msg)))

    controller.load_winapp_rules(str(ini))  # must not raise

    deadline = time.monotonic() + 30
    while not seen and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert seen, "winapp_loaded was never delivered"
    assert isinstance(seen[0], int) and seen[0] >= 0, f"bad payload: {seen[0]!r}"
