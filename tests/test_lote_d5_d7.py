"""Lote D5-D7 regression tests.

D5 - SafetyGuard critical-file deny-list: OS-critical files are refused
     everywhere by basename, and the OS binary trees (System32, SysWOW64,
     Boot) refuse every descendant; whitelisted cleanable sub-trees
     (LogFiles, spool PRINTERS, winevt Logs) stay cleanable for files.
D6 - Audit coverage + batching: AuditLogger.batched() collapses the
     per-record open/append/close into periodic single writes; every
     destructive operation now records a per-batch "summary" (duplicates
     and uninstall leftovers previously logged NOTHING).
D7 - Root-level scan parallelism: _scan_rules and the plain-location
     scan run their roots/locations through _parallel_map with
     deterministic (order-independent) summation.

Style: tmp_path + fakes, following the repo's test conventions (no
QApplication: libEGL is unavailable in the Linux CI container).
"""

import json
import os
from types import SimpleNamespace

import pytest

from limpiapro import categories as categories_mod
from limpiapro import duplicates as duplicates_mod
from limpiapro import uninstall as uninstall_mod
from limpiapro.audit_log import _BATCH_FLUSH_EVERY, AuditLogger
from limpiapro.categories import CleanCategory
from limpiapro.safety import (
    SafetyGuard,
    invalidate_safety_guard,
    safety_guard,
)
from limpiapro.utils import _delete_measured
from limpiapro.winapp2 import WinAppRule


@pytest.fixture(autouse=True)
def _profile_is_tmp(tmp_path, monkeypatch):
    """Point USERPROFILE at the scratch dir and reset the guard singleton
    (same convention as test_safety_guard.py)."""
    monkeypatch.delenv("SystemRoot", raising=False)
    monkeypatch.delenv("WINDIR", raising=False)
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    invalidate_safety_guard()
    yield
    invalidate_safety_guard()


def _fresh_audit(tmp_path):
    """A private AuditLogger writing into tmp_path (no global state)."""
    a = AuditLogger()
    a._log_path = tmp_path / "audit.jsonl"
    return a


def _records(path):
    """Parse an audit JSONL file into dicts."""
    return [json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


# ----------------------------------------------------------------- D5


class TestD5CriticalDenyList:

    def test_critical_basenames_refused_anywhere(self, tmp_path):
        guard = safety_guard()
        for name in ("kernel32.dll", "explorer.exe", "ntuser.dat",
                     "pagefile.sys", "cmd.exe"):
            assert guard.is_safe_delete_target(
                str(tmp_path / name), is_dir=False) is False, name
        assert guard.is_safe_delete_target(
            r"C:\Windows\System32\kernel32.dll", is_dir=False) is False
        assert guard.is_safe_delete_target(
            r"C:\Windows\explorer.exe", is_dir=False) is False

    def test_system32_descendants_refused(self):
        guard = safety_guard()
        assert guard.is_safe_delete_target(
            r"C:\Windows\System32\evil.dll", is_dir=False) is False
        assert guard.is_safe_delete_target(
            r"C:\Windows\SysWOW64\evil.dll", is_dir=False) is False
        assert guard.is_safe_delete_target(
            r"C:\Windows\Boot\EFI\somefile", is_dir=False) is False
        # Folders: no exemptions at all inside the OS binary trees.
        assert guard.is_safe_delete_target(
            r"C:\Windows\System32\somesub", is_dir=True) is False
        assert guard.is_safe_delete_target(
            r"C:\Windows\System32\spool\PRINTERS", is_dir=True) is False

    def test_system32_whitelisted_subtrees_cleanable(self):
        guard = safety_guard()
        assert guard.is_safe_delete_target(
            r"C:\Windows\System32\LogFiles\httperr\err.log",
            is_dir=False) is True
        assert guard.is_safe_delete_target(
            r"C:\Windows\System32\spool\PRINTERS\00001.SHD",
            is_dir=False) is True
        assert guard.is_safe_delete_target(
            r"C:\Windows\System32\winevt\Logs\App.evtx",
            is_dir=False) is True

    def test_windows_dir_loose_files_refused_but_temp_cleanable(self):
        guard = safety_guard()
        assert guard.is_safe_delete_target(
            r"C:\Windows\win.ini", is_dir=False) is False
        assert guard.is_safe_delete_target(
            r"C:\Windows\explorer.exe", is_dir=False) is False
        # Legitimate Windows-area cleaning targets stay cleanable.
        assert guard.is_safe_delete_target(
            r"C:\Windows\Temp\cleanme.tmp", is_dir=False) is True
        assert guard.is_safe_delete_target(
            r"C:\Windows\Prefetch\APP.EXE-123.pf", is_dir=False) is True
        assert guard.is_safe_delete_target(
            r"C:\Windows\SoftwareDistribution\Download\pkg.bin",
            is_dir=False) is True

    def test_case_and_separator_robustness(self):
        guard = safety_guard()
        assert guard.is_safe_delete_target(
            r"c:/windows/system32/SOMETHING.dll", is_dir=False) is False
        assert guard.is_safe_delete_target(
            r"C:\WINDOWS\SYSTEM32\KERNEL32.DLL", is_dir=False) is False
        assert guard.is_safe_delete_target(
            r"C:/Windows/System32/LogFiles/app.log", is_dir=False) is True

    def test_systemroot_env_honoured(self, monkeypatch):
        monkeypatch.setenv("SystemRoot", r"D:\Win")
        guard = SafetyGuard()
        guard.invalidate()
        assert guard.is_safe_delete_target(
            r"D:\Win\System32\evil.dll", is_dir=False) is False
        assert guard.is_safe_delete_target(
            r"D:\Win\System32\LogFiles\x.log", is_dir=False) is True
        assert guard.is_safe_delete_target(
            r"D:\Win\loose.ini", is_dir=False) is False

    def test_delete_measured_refuses_real_critical_file(self, tmp_path):
        victim = tmp_path / "kernel32.dll"
        victim.write_text("fake", encoding="utf-8")
        gone, _freed, errors = _delete_measured(str(victim))
        assert gone is False
        assert errors and errors[0].kind == "safety"
        assert victim.exists()

    def test_existing_policy_untouched(self, tmp_path):
        guard = safety_guard()
        # Exact system root stays refused; ordinary files stay cleanable.
        assert guard.is_safe_delete_target(r"C:\Windows\System32") is False
        assert guard.is_safe_delete_target(
            str(tmp_path / "normal.log"), is_dir=False) is True


# ----------------------------------------------------------------- D6


class TestD6AuditBatching:

    def test_batched_defers_writes_until_exit(self, tmp_path):
        a = _fresh_audit(tmp_path)
        with a.batched():
            for i in range(10):
                a.log_operation(operation="cleanup", category="c",
                                path=f"/t/f{i}")
            assert not a._log_path.exists()  # buffered, not on disk yet
        assert len(_records(a._log_path)) == 10

    def test_batched_autoflush_at_threshold(self, tmp_path):
        a = _fresh_audit(tmp_path)
        total = _BATCH_FLUSH_EVERY + 6
        with a.batched():
            for _ in range(total):
                a.log_operation(operation="cleanup", category="c")
            assert len(_records(a._log_path)) >= _BATCH_FLUSH_EVERY
        assert len(_records(a._log_path)) == total

    def test_batched_flushes_on_exception(self, tmp_path):
        a = _fresh_audit(tmp_path)
        with pytest.raises(RuntimeError), a.batched():
            a.log_operation(operation="scan", category="c")
            raise RuntimeError("boom")
        assert len(_records(a._log_path)) == 1

    def test_outside_batch_writes_immediately(self, tmp_path):
        a = _fresh_audit(tmp_path)
        a.log_operation(operation="preview", category="c")
        assert len(_records(a._log_path)) == 1

    def test_batched_output_is_valid_jsonl(self, tmp_path):
        a = _fresh_audit(tmp_path)
        with a.batched():
            for i in range(_BATCH_FLUSH_EVERY * 2 + 3):
                a.log_operation(operation="cleanup", category="c",
                                path=f"/t/{i}")
        recs = _records(a._log_path)
        assert len(recs) == _BATCH_FLUSH_EVERY * 2 + 3
        assert all(r["operation"] == "cleanup" for r in recs)


class TestD6AuditCoverage:

    def test_clean_writes_summary_record(self, tmp_path, monkeypatch):
        a = _fresh_audit(tmp_path)
        monkeypatch.setattr(categories_mod, "audit", a)
        loc = tmp_path / "loc"
        loc.mkdir()
        (loc / "f1.bin").write_bytes(b"x" * 100)
        (loc / "f2.bin").write_bytes(b"y" * 50)
        cat = CleanCategory("catkey", "C", "", [str(loc)])
        removed, errors, freed = cat.clean()
        assert (removed, errors, freed) == (2, 0, 150)
        recs = _records(a._log_path)
        summaries = [r for r in recs if r.get("action") == "summary"]
        assert len(summaries) == 1
        s = summaries[0]
        assert s["operation"] == "cleanup" and s["category"] == "catkey"
        assert s["details"]["removed"] == 2
        assert s["details"]["errors"] == 0
        assert s["details"]["freed_bytes"] == 150
        assert s["details"]["mode"] == "delete"

    def test_clean_summary_reports_recycle_mode(self, tmp_path, monkeypatch):
        a = _fresh_audit(tmp_path)
        monkeypatch.setattr(categories_mod, "audit", a)
        loc = tmp_path / "loc2"
        loc.mkdir()
        (loc / "f.bin").write_bytes(b"z" * 10)
        cat = CleanCategory("catkey", "C", "", [str(loc)])
        # to_recycle=True requires send2trash; in this environment the
        # movement itself may fail (fail-safe), but the summary must
        # still record the mode honestly.
        cat.clean(to_recycle=True)
        recs = _records(a._log_path)
        summaries = [r for r in recs if r.get("action") == "summary"]
        assert len(summaries) == 1
        assert summaries[0]["details"]["mode"] == "recycle"

    def test_delete_duplicates_audits_summary_and_skips_changed(
            self, tmp_path, monkeypatch):
        a = _fresh_audit(tmp_path)
        monkeypatch.setattr(duplicates_mod, "audit", a)
        f1 = tmp_path / "a.dat"
        f1.write_bytes(b"same" * 10)          # 40 bytes
        f2 = tmp_path / "b.dat"
        f2.write_bytes(b"same" * 10)
        snap = {}
        for p in (f1, f2):
            st = os.stat(p)
            snap[str(p)] = (st.st_size, st.st_mtime_ns)
        f2.write_bytes(b"d" * 41)             # modified AFTER the scan
        removed, errors, changed = duplicates_mod.delete_duplicates(
            [str(f1), str(f2)], snap)
        assert (removed, errors, changed) == (1, 0, 1)
        assert not f1.exists() and f2.exists()
        recs = _records(a._log_path)
        summaries = [r for r in recs if r.get("action") == "summary"]
        assert len(summaries) == 1
        det = summaries[0]["details"]
        assert det["removed"] == 1 and det["changed"] == 1
        assert det["freed_bytes"] == 40 and det["mode"] == "delete"
        # No per-file SUCCESS records: the I/O amplification pattern stays dead.
        assert not [r for r in recs
                    if r.get("action") == "delete" and r["result"] == "success"]

    def test_delete_duplicates_records_failures(self, tmp_path, monkeypatch):
        a = _fresh_audit(tmp_path)
        monkeypatch.setattr(duplicates_mod, "audit", a)
        f = tmp_path / "gone.dat"
        f.write_bytes(b"x" * 8)
        st = os.stat(f)
        snap = {str(f): (st.st_size, st.st_mtime_ns)}
        monkeypatch.setattr(
            duplicates_mod, "_delete_measured",
            lambda p, to_recycle=False: (
                False, 0,
                [SimpleNamespace(path=p, code=5, message="access denied",
                                 operation="unlink",
                                 kind="access_denied")]))
        removed, errors, changed = duplicates_mod.delete_duplicates(
            [str(f)], snap)
        assert (removed, errors, changed) == (0, 1, 0)
        fails = [r for r in _records(a._log_path) if r["result"] == "failed"]
        assert len(fails) == 1
        assert fails[0]["error_code"] == 5
        assert fails[0]["details"]["kind"] == "access_denied"

    def test_delete_leftover_items_audits_files_and_registry(
            self, tmp_path, monkeypatch):
        a = _fresh_audit(tmp_path)
        monkeypatch.setattr(uninstall_mod, "audit", a)
        monkeypatch.setattr(uninstall_mod, "delete_registry_path",
                            lambda p: False)  # deterministic refusal
        f1 = tmp_path / "leftover.ini"
        f1.write_text("data", encoding="utf-8")
        ok, err = uninstall_mod.delete_leftover_items([
            ("file", str(f1)),
            ("registry", r"HKCU\Software\FakeApp"),
        ])
        assert (ok, err) == (1, 1)
        assert not f1.exists()
        recs = _records(a._log_path)
        fails = [r for r in recs if r["result"] == "failed"]
        assert len(fails) == 1
        assert fails[0]["operation"] == "uninstall"
        assert fails[0]["details"]["kind"] == "registry"
        summaries = [r for r in recs if r.get("action") == "summary"]
        assert len(summaries) == 1
        assert summaries[0]["details"]["removed"] == 1
        assert summaries[0]["details"]["errors"] == 1


# ----------------------------------------------------------------- D7


def _make_roots(d):
    """Three roots, each with a.log (100/200/300 bytes) + b.txt (10 bytes)."""
    for i in range(3):
        sub = d / f"root{i}"
        sub.mkdir()
        (sub / "a.log").write_text("x" * (100 * (i + 1)))
        (sub / "b.txt").write_text("y" * 10)


class TestD7ParallelScan:

    def test_scan_rules_uses_parallel_roots(self, tmp_path, monkeypatch):
        calls = []
        real = categories_mod._parallel_map

        def spy(func, items, workers=None):
            items = list(items)
            calls.append(len(items))
            return real(func, items, workers)

        monkeypatch.setattr(categories_mod, "_parallel_map", spy)
        _make_roots(tmp_path)
        cat = CleanCategory("k", "K", "", [])
        cat.rules = [WinAppRule(root=str(tmp_path / f"root{i}"),
                                recurse=True, patterns=("*.log",))
                     for i in range(3)]
        assert cat.scan() == 600
        assert cat.files == 3
        assert calls == [3]  # one parallel batch over the 3 roots

    def test_plain_scan_uses_parallel_locations(self, tmp_path, monkeypatch):
        calls = []
        real = categories_mod._parallel_map

        def spy(func, items, workers=None):
            items = list(items)
            calls.append(len(items))
            return real(func, items, workers)

        monkeypatch.setattr(categories_mod, "_parallel_map", spy)
        _make_roots(tmp_path)
        cat = CleanCategory(
            "p", "P", "", [str(tmp_path / f"root{i}") for i in range(3)])
        assert cat.scan() == 630
        assert cat.files == 6
        assert calls == [3]

    def test_progress_reported_per_location(self, tmp_path):
        _make_roots(tmp_path)
        got = []
        cat = CleanCategory(
            "q", "Q", "", [str(tmp_path / f"root{i}") for i in range(3)])
        cat.scan(on_progress=got.append)
        assert got == [2, 4, 6]  # running totals, deterministic order

    def test_scan_rules_progress_reported(self, tmp_path):
        _make_roots(tmp_path)
        got = []
        cat = CleanCategory("k", "K", "", [])
        cat.rules = [WinAppRule(root=str(tmp_path / f"root{i}"),
                                recurse=True, patterns=("*.log",))
                     for i in range(3)]
        cat.scan(on_progress=got.append)
        assert got == [1, 2, 3]

    def test_plain_scan_tolerates_worker_crash(self, tmp_path, monkeypatch):
        _make_roots(tmp_path)
        real_stats = categories_mod._fast_folder_stats

        def flaky(folder, on_progress=None, should_cancel=None):
            if folder.endswith("root1"):
                raise RuntimeError("worker crash")
            return real_stats(folder, on_progress, should_cancel)

        monkeypatch.setattr(categories_mod, "_fast_folder_stats", flaky)
        cat = CleanCategory(
            "p", "P", "", [str(tmp_path / f"root{i}") for i in range(3)])
        # root1 contributes nothing (None); the others still count.
        assert cat.scan() == 420
        assert cat.files == 4

    def test_scan_rules_tolerates_none_results(self, monkeypatch):
        monkeypatch.setattr(
            categories_mod, "_parallel_map",
            lambda func, items, workers=None: [None, (5, 1)])
        cat = CleanCategory("k", "K", "", [])
        cat.rules = [WinAppRule(root="/definitely/missing/root",
                                recurse=True, patterns=("*",))]
        assert cat.scan() == 5
        assert cat.files == 1

    def test_cancellation_yields_empty_scan(self, tmp_path):
        _make_roots(tmp_path)
        cat = CleanCategory("k", "K", "", [])
        cat.rules = [WinAppRule(root=str(tmp_path / f"root{i}"),
                                recurse=True, patterns=("*",))
                     for i in range(3)]
        total = cat.scan(should_cancel=lambda: True)
        assert total == 0
        assert cat.files == 0

    def test_plain_scan_cancellation(self, tmp_path):
        _make_roots(tmp_path)
        cat = CleanCategory(
            "p", "P", "", [str(tmp_path / f"root{i}") for i in range(3)])
        total = cat.scan(should_cancel=lambda: True)
        assert total == 0
        assert cat.files == 0
