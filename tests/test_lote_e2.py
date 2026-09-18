"""Tests for Lote E2: heavy work off the first paint + two-tier schtasks.

E2.1: the bundled winapp2.ini must NOT be parsed during category build /
controller construction when deferred; the UI loads it on a worker after
the first paint. E2.2: the WinSxS walk runs only on user action. E2.3:
the schtasks table fills from the fast non-verbose query and the
disabled state merges asynchronously from the verbose one.
"""

import re
from pathlib import Path

from limpiapro import tasks
from limpiapro.tasks import get_scheduled_tasks, get_task_states

REPO = Path(__file__).resolve().parent.parent


class _FakeResult:
    def __init__(self, stdout):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = 0


# ------------------------------------------------------------ E2.3 fast

FAST_CSV = (
    # Header (localized names, language-independent filter handles it):
    '"HostName","TaskName","Next Run Time","Status"\n'
    '"PC","\\Microsoft\\Windows\\Defrag\\ScheduledDefrag",'
    '"2026-09-05 03:00","Listo"\n'
    '"Tarea","Estado"\n'                 # junk: localized header repeat
    '"PC","\\MiTarea","N/A",""\n'
    '"PC","SinBarra","x","x"\n'          # junk: no leading backslash
    '"corto"\n'                          # malformed row
)

VERBOSE_CSV = (
    '"HostName","TaskName","Next Run Time","Status","Logon Mode",'
    '"Last Run Time","Last Result","Creator","Task To Run","Start In",'
    '"Comments","Scheduled Task State"\n'
    '"PC","\\Microsoft\\Windows\\Defrag\\ScheduledDefrag","x","x","x",'
    '"x","x","x","x","x","x","Enabled"\n'
    '"PC","\\MiTarea","x","x","x","x","x","x","x","x","x","Disabled"\n'
    '"corto"\n'
)


def test_fast_query_does_not_use_verbose(monkeypatch):
    seen = {}

    def fake_cmd(args, timeout=60):
        seen["args"] = args
        return _FakeResult(FAST_CSV)

    monkeypatch.setattr(tasks, "run_system_cmd", fake_cmd)
    got = get_scheduled_tasks()
    assert "/v" not in seen["args"], "the fast query must not pay for /v"
    assert [t["name"] for t in got] == [
        "\\Microsoft\\Windows\\Defrag\\ScheduledDefrag", "\\MiTarea"]
    assert got[0]["status"] == "Listo"
    assert got[0]["next"] == "2026-09-05 03:00"
    assert got[0]["scheduled"] == ""  # arrives later via get_task_states
    assert all("path" not in t for t in got), "dead verbose column removed"


def test_verbose_states_query(monkeypatch):
    seen = {}

    def fake_cmd(args, timeout=60):
        seen["args"] = args
        return _FakeResult(VERBOSE_CSV)

    monkeypatch.setattr(tasks, "run_system_cmd", fake_cmd)
    states = get_task_states()
    assert "/v" in seen["args"]
    assert states == {
        "\\Microsoft\\Windows\\Defrag\\ScheduledDefrag": "Enabled",
        "\\MiTarea": "Disabled",
    }


def test_query_errors_are_swallowed_with_log(monkeypatch):
    def boom(args, timeout=60):
        raise RuntimeError("schtasks missing")

    monkeypatch.setattr(tasks, "run_system_cmd", boom)
    assert get_scheduled_tasks() == []
    assert get_task_states() == {}


# ------------------------------------------------- E2.1 deferred winapp2


def test_build_categories_deferred_never_parses(monkeypatch):
    import limpiapro.categories as cats_mod

    def boom(*_a, **_k):
        raise AssertionError("parser ran although deferred")

    monkeypatch.setattr(cats_mod, "parse_winapp_rules", boom)
    cats = cats_mod.build_categories(load_winapp=False)
    winapp = [c for c in cats if c.key == "winapp"]
    assert len(winapp) == 1
    assert winapp[0].rules == []


def test_build_categories_default_goes_through_parser(monkeypatch):
    import limpiapro.categories as cats_mod

    called = []

    def fake_parse(path):
        called.append(path)
        return []

    monkeypatch.setattr(cats_mod, "parse_winapp_rules", fake_parse)
    cats = cats_mod.build_categories()
    assert called, "the default build must parse the bundled ini"
    assert any(c.key == "winapp" and c.rules == [] for c in cats)


def test_controller_defer_winapp(tmp_path):
    from limpiapro.controller import LimpiaProController
    from limpiapro.services import CacheService

    ctrl = LimpiaProController(
        cache_service=CacheService(tmp_path / "c.json", 1, "t"),
        defer_winapp=True)
    winapp = next(c for c in ctrl.categories if c.key == "winapp")
    assert winapp.rules == []
    # Other categories are unaffected by the deferral.
    assert {c.key for c in ctrl.categories} >= {
        "temp", "browser", "apps", "history", "winapp"}


# ------------------------------------------------------- E2.1/E2.2 wiring


def test_main_window_wiring_guards():
    """Source guards (no QApplication in this environment): the window
    must build a deferred controller and sequence the analysis behind
    the winapp load."""
    src = (REPO / "limpiapro" / "ui" / "main_window.py").read_text(
        encoding="utf-8")
    assert "_LPC(defer_winapp=True)" in src
    assert "_startup_winapp_load" in src
    assert "_auto_analyze_pending" in src
    # The manual ini load keeps its historical behavior (analyze after).
    assert "_winapp_load_is_startup = False" in src


def test_update_page_measures_only_on_demand():
    src = (REPO / "limpiapro" / "ui" / "pages" / "update_page.py"
           ).read_text(encoding="utf-8")
    # Exactly one measurement trigger, inside _measure_if_needed.
    assert len(re.findall(r"run_async\(self, self\._measure", src)) == 1
    assert "_measure_if_needed" in src
    assert "self._measured = False" in src
    # The tab must NOT start measuring on construction: __init__ body
    # has no run_async call.
    init_body = src.split("def __init__", 1)[1].split(
        "# -------------------------------------------------------------",
        1)[0]
    assert "run_async" not in init_body
