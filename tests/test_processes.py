"""tasklist-without-/v regressions (B3 perf fix).

`tasklist /v` queried window titles, users and CPU times for every
process: seconds of latency (effectively a hang when a process never
answers the title query). The plain CSV listing answers fast; the UI
lost only the "user" column, which was removed from the table.

The parser must also reject the localized header row WITHOUT relying
on words (the tasks.py lesson): a data row always has a numeric PID,
headers never do.
"""

from __future__ import annotations

from types import SimpleNamespace

import limpiapro.processes as processes

# Real `tasklist /fo CSV` shape on a Spanish Windows (header + 2 data
# rows, 5 columns; no /v). The header is localized; PID is not.
_ES_CSV = (
    '"Nombre de imagen","PID","Nombre de sesi\xc3\xb3n",'
    '"N\xc3\xbamero de sesi\xc3\xb3n","Uso de memoria"\n'
    '"explorer.exe","4012","Console","1","95.320 K"\n'
    '"chrome.exe","8124","Console","1","412.108 K"\n'
)

_EN_HEADER_ONLY = (
    '"Image Name","PID","Session Name","Session#","Mem Usage"\n'
)


def _run(monkeypatch, stdout, cmd_log):
    def fake_run_system_cmd(cmd, **_kwargs):
        cmd_log.append(list(cmd))
        return SimpleNamespace(stdout=stdout, returncode=0, stderr="")

    monkeypatch.setattr(processes, "run_system_cmd", fake_run_system_cmd)


def test_command_has_no_verbose_flag(monkeypatch):
    """Regression guard: get_processes must not pay for /v ever again."""
    log = []
    _run(monkeypatch, _ES_CSV, log)
    processes.get_processes()
    assert log == [["tasklist", "/fo", "CSV"]]
    assert "/v" not in log[0]


def test_localized_header_row_is_skipped(monkeypatch):
    log = []
    _run(monkeypatch, _ES_CSV, log)
    procs = processes.get_processes()

    names = [p["name"] for p in procs]
    assert names == ["explorer.exe", "chrome.exe"]
    # The localized header must not leak in as a fake process either.
    assert all(p["pid"].isdigit() for p in procs)


def test_english_header_only_yields_no_processes(monkeypatch):
    log = []
    _run(monkeypatch, _EN_HEADER_ONLY, log)
    assert processes.get_processes() == []


def test_rows_are_parsed_with_expected_fields(monkeypatch):
    log = []
    _run(monkeypatch, _ES_CSV, log)
    procs = processes.get_processes()

    first = procs[0]
    assert first == {
        "name": "explorer.exe",
        "pid": "4012",
        "session": "Console",
        "mem": "95.320 K",
        "user": "",
        "title": "",
    }


def test_malformed_and_nonnumeric_pid_rows_are_skipped(monkeypatch):
    junk = (
        '"Nombre","PID","Sesion","Num","Mem"\n'
        '"short row","12"\n'
        '"not a pid","PID!","Console","1","1 K"\n'
        '"ok.exe","99","Services","0","2 K"\n'
    )
    log = []
    _run(monkeypatch, junk, log)
    procs = processes.get_processes()
    assert [p["pid"] for p in procs] == ["99"]


def test_command_failure_yields_empty_list(monkeypatch):
    log = []

    def failing_cmd(_cmd, **_kwargs):
        log.append(1)
        raise OSError("tasklist exploded")

    monkeypatch.setattr(processes, "run_system_cmd", failing_cmd)
    assert processes.get_processes() == []
    assert log  # the failure path was actually exercised


def test_name_for_resolves_pid_from_plain_listing(monkeypatch):
    log = []
    _run(monkeypatch, _ES_CSV, log)
    assert processes._name_for("8124") == "chrome.exe"
    assert processes._name_for("1") == ""
