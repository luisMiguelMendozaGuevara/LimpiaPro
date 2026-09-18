"""Lote D regressions: clean-worker crash safety, post-clean cache
freshness and error-log transparency/thread-safety (D1-D4).

D2 - CleanWorker.run must never die with an unhandled exception: the
     failed signal surfaces the error and releases the busy state (the
     same contract AnalysisWorker/PreviewWorker/TaskWorker already had).
     The worker orchestration runs synchronously without a QApplication
     (same approach as test_controller.py).
D3 - finishing a clean persists the POST-clean sizes into the scan
     cache; the next startup's incremental analysis must not present
     pre-clean sizes as fresh "cached" results.
D4 - _errlog serializes rotation+append behind a lock (well-formed JSONL
     under concurrent writers) and delete_registry_path logs why it
     failed instead of returning an opaque False.
"""

from __future__ import annotations

import json
import threading

from limpiapro import uninstall, utils
from limpiapro.controller import (
    CleanWorker,
    LimpiaProController,
    _cache_payload,
)
from limpiapro.services import CacheService


class _FakeCategory:
    """Minimal duck-typed CleanCategory for the worker tests."""

    def __init__(self, key="tmp", size=123, files=7, label="Tmp",
                 explode=False):
        self.key = key
        self.label = label
        self.description = ""
        self.icon = ""
        self.size = size
        self.files = files
        self.needs_admin = False
        self.recycle_bin = False
        self._snapshot = None
        self._explode = explode

    def list_files(self, limit: int = 1000):
        return ([], 0)

    def clean(self, target_bytes=0, to_recycle=False, on_progress=None,
              should_cancel=None):
        if self._explode:
            raise RuntimeError("boom: unexpected failure")
        # Mirror CleanCategory.clean(): sizes updated in place with the
        # freed bytes, so the controller's post-clean snapshot is real.
        self.size = 0
        self.files = 0
        return (3, 0, target_bytes)


# ----------------------------------------------------------- D2 crash gate

def test_clean_worker_emits_failed_and_never_finished_on_crash():
    worker = CleanWorker([_FakeCategory(explode=True)], lambda: False)
    events: dict[str, list] = {"failed": [], "finished": []}
    worker.failed.connect(events["failed"].append)
    worker.finished.connect(events["finished"].append)

    worker.run()

    assert len(events["failed"]) == 1
    assert "boom" in events["failed"][0]
    assert events["finished"] == []


def test_clean_crash_releases_busy_and_reports_operation_error(
        monkeypatch):
    controller = LimpiaProController(categories=[_FakeCategory(explode=True)])
    started: list = []
    # Run the orchestration synchronously: capture the worker instead of
    # moving it to a real QThread (repo pattern from test_controller.py).
    monkeypatch.setattr(
        LimpiaProController, "_start_worker",
        lambda self, worker, *terminal: started.append(worker))
    errors: list = []
    controller.operation_error.connect(errors.append)

    controller.clean(["tmp"])
    assert controller.busy  # wiring went through the normal busy path

    started[0].run()  # simulate the worker thread synchronously

    assert not controller.busy  # D2: UI released, not stuck on "busy"
    assert errors and "boom" in errors[0]


def test_clean_success_still_emits_finished_summary():
    worker = CleanWorker([_FakeCategory(size=100)], lambda: False)
    summary: list = []
    worker.finished.connect(summary.append)

    worker.run()

    assert len(summary) == 1 and summary[0].removed == 3


# ------------------------------------------------ D3 post-clean cache

def test_clean_finish_saves_post_clean_sizes(monkeypatch, tmp_path):
    svc = CacheService(tmp_path / "cache.json", schema=1, app_version="t")
    cat = _FakeCategory(key="tmp", size=123, files=7)
    controller = LimpiaProController(categories=[cat], cache_service=svc)
    started: list = []
    monkeypatch.setattr(
        LimpiaProController, "_start_worker",
        lambda self, worker, *terminal: started.append(worker))

    controller.clean(["tmp"])
    started[0].run()

    # 123 (pre-clean) must have been replaced by the post-clean sizes.
    assert svc.load()["tmp"] == {"size": 0, "files": 0}


def test_cache_payload_helper_shapes_data():
    cats = [_FakeCategory(key="a", size=1, files=2),
            _FakeCategory(key="b", size=3, files=4)]
    assert _cache_payload(cats) == {
        "a": {"size": 1, "files": 2},
        "b": {"size": 3, "files": 4},
    }


# ---------------------------------------------------- D4 error logging

def test_errlog_survives_concurrent_writers(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_logs_dir", lambda: str(tmp_path))
    threads_n, per_thread = 8, 25

    def burst(i: int) -> None:
        for j in range(per_thread):
            utils._errlog(f"worker {i} line {j}", component="t")

    threads = [threading.Thread(target=burst, args=(i,))
               for i in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = (tmp_path / "limpiapro_error.log").read_text(
        encoding="utf-8").splitlines()
    assert len(lines) == threads_n * per_thread  # none lost/interleaved
    for line in lines:
        record = json.loads(line)  # every line is well-formed JSON
        assert record["component"] == "t"


def test_delete_registry_path_logs_why_it_failed(monkeypatch):
    logged: list = []
    monkeypatch.setattr(uninstall, "_errlog", lambda m, **k: logged.append(m))

    def _raise(*_a, **_k):
        raise RuntimeError("registry locked by test")

    monkeypatch.setattr(uninstall.winreg, "OpenKey", _raise)

    assert uninstall.delete_registry_path("HKCU\\Software\\SomeApp") is False
    assert logged and "reg delete failed" in logged[0]
    assert "registry locked" in logged[0]
