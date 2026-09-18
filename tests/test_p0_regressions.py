"""Regression tests for the four P0 defects fixed after v2.5.

Each test class pins one verified bug:

1. tasks.get_scheduled_tasks — the old localized-word filter
   ("tarea" in name.lower()) HID legitimate tasks on a Spanish Windows
   (e.g. "\\MiTareaDiaria\\Ejecutar") while failing to filter repeated
   localized headers in other languages. The language-independent rule
   is: data rows always start with '\', junk rows never do.

2. startup._reg_transfer / _read_reg_value — moved registry values were
   rewritten as REG_SZ with str(value), corrupting REG_EXPAND_SZ (stops
   env-var expansion: the app stops launching), REG_BINARY and REG_DWORD
   entries across a disable -> enable roundtrip.

3. processes.kill_process — the safety gate failed OPEN: when the process
   name could not be resolved, is_protected("") returned False and the
   PID was force-killed anyway by an admin-privileged taskkill.

4. utils._iter_tree_files — cancellation returned from mid-walk without
   closing the still-open os.scandir iterators; on Windows an open
   directory handle blocks later deletion/rename of that folder.
"""

import csv
import io
import os

import pytest

from limpiapro import processes, startup, tasks, utils


class _CmdResult:
    """Minimal run_system_cmd() stand-in (.stdout/.stderr/.returncode)."""

    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _schtasks_csv(rows):
    """Build 12-column CSV lines the way schtasks writes them."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf)
    for r in rows:
        w.writerow(r)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 1) tasks.py — localized "tarea" filter must not hide real tasks
# ---------------------------------------------------------------------------

HEADER = ["HOSTNAME"] + [f"col{i}" for i in range(1, 12)]


class TestScheduledTaskFilter:
    def _rows(self):
        return [t["name"] for t in tasks.get_scheduled_tasks()]

    def test_task_with_tarea_in_name_is_listed(self, monkeypatch):
        """A Spanish-named task containing 'tarea' MUST appear (was hidden)."""
        row = ["PC", r"\MiTareaDiaria\Ejecutar", "2026-01-01 00:00", "Listo",
               "En línea", "2025-12-31", "0", "Autor",
               r"C:\backup.cmd", "C:\\", "comentario",
               "Preparada"]
        fake = _CmdResult(stdout=_schtasks_csv([HEADER, row]))
        monkeypatch.setattr(tasks, "run_system_cmd", lambda *_a, **_k: fake)

        names = self._rows()
        assert names == [r"\MiTareaDiaria\Ejecutar"]

    def test_localized_header_repeat_still_filtered(self, monkeypatch):
        """Repeated localized header/junk rows stay filtered: their 'name'
        never starts with '\' (works in any UI language)."""
        junk_header = ["HOSTNAME", "Tarea", "Siguiente hora de ejecución",
                       "Estado", "Modo", "Última hora", "Último resultado",
                       "Autor", "Tarea que se va a ejecutar", "Inicio",
                       "Comentario", "Estado de tarea programada"]
        junk_empty_name = ["PC", "", "07:00", "Listo", *["x"] * 8]
        good = ["PC", r"\Microsoft\Windows\Defrag\ScheduledDefrag",
                "2026-08-27 03:00", "Listo", "Interactiva", "2026-08-26",
                "0", "Microsoft", "defragsvc.exe", "-",
                "-", "Habilitada"]
        fake = _CmdResult(stdout=_schtasks_csv(
            [HEADER, junk_header, junk_empty_name, good]))
        monkeypatch.setattr(tasks, "run_system_cmd", lambda *_a, **_k: fake)

        names = self._rows()
        assert names == [r"\Microsoft\Windows\Defrag\ScheduledDefrag"]

    def test_malformed_row_skipped(self, monkeypatch):
        # Fast query (E2.3): the CSV carries 4 columns, so a row with
        # fewer than 4 fields is the malformed case (it used to be <12
        # when the verbose query fed the table).
        short = ["PC", r"\Broken\Row", "only"]
        good = ["PC", r"\Ok", "n", "s"]
        fake = _CmdResult(stdout=_schtasks_csv([HEADER, short, good]))
        monkeypatch.setattr(tasks, "run_system_cmd", lambda *_a, **_k: fake)

        names = self._rows()
        assert names == [r"\Ok"]

    def test_non_backslash_names_filtered_even_with_tarea_word(self, monkeypatch):
        """'Tâche...' / 'Aufgabe...' header repeats are also dropped."""
        fr_junk = ["PC", "Tâche à exécuter", "prochaine", "État",
                   *["x"] * 8]
        good = ["PC", r"\WindowsErrorReporting", "n", "s", "m", "l", "0",
                "a", "p.exe", ".", "c", "Enabled"]
        fake = _CmdResult(stdout=_schtasks_csv([HEADER, fr_junk, good]))
        monkeypatch.setattr(tasks, "run_system_cmd", lambda *_a, **_k: fake)

        names = self._rows()
        assert names == [r"\WindowsErrorReporting"]


# ---------------------------------------------------------------------------
# 2) startup.py — registry value types preserved across disable/enable
# ---------------------------------------------------------------------------

class FakeKey:
    def __init__(self, registry, hive, subkey):
        self.registry = registry
        self.hive = hive
        self.subkey = subkey

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeRegistry:
    """In-memory winreg substitute (mirrors tests/test_startup_registry.py)."""

    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"
    KEY_SET_VALUE = 2
    REG_SZ = 1
    REG_EXPAND_SZ = 2
    REG_BINARY = 3
    REG_DWORD = 4

    def __init__(self):
        # {(hive, subkey, name): (data, type)}
        self.values = {}
        self.fail_delete_subkeys = set()

    def CreateKey(self, hive, subkey):
        return FakeKey(self, hive, subkey)

    def OpenKey(self, hive, subkey, *_args):
        return FakeKey(self, hive, subkey)

    def QueryValueEx(self, key, name):
        try:
            return self.values[(key.hive, key.subkey, name)]
        except KeyError as exc:
            raise OSError("missing") from exc

    def SetValueEx(self, key, name, _reserved, value_type, value):
        self.values[(key.hive, key.subkey, name)] = (value, value_type)

    def DeleteValue(self, key, name):
        if key.subkey in self.fail_delete_subkeys:
            raise OSError("delete failed")
        self.values.pop((key.hive, key.subkey, name), None)


@pytest.fixture()
def fakereg(monkeypatch):
    fake = FakeRegistry()
    monkeypatch.setattr(startup, "winreg", fake)
    return fake


class TestRegistryTypePreservation:
    RUN_NAME = "MyApp"
    RUN_PATH_EXPAND = r"%ProgramFiles%\MyApp\app.exe"

    def _active_key(self):
        h, subkey, _src = startup.RUN_KEYS[0]
        return h, subkey

    def _disabled_key(self):
        h, active = self._active_key()
        return startup.RUN_KEY_TO_DISABLED[(h, active)]

    @pytest.mark.parametrize("data,dtype", [
        pytest.param(r"%ProgramFiles%\App\app.exe",
                     FakeRegistry.REG_EXPAND_SZ, id="expand_sz"),
        pytest.param(b"\x00\x01\xffbin\x00", FakeRegistry.REG_BINARY,
                     id="binary"),
        pytest.param(251658240, FakeRegistry.REG_DWORD, id="dword"),
        pytest.param(r"C:\plain path\app.exe", FakeRegistry.REG_SZ,
                     id="sz"),
    ])
    def test_disable_enable_roundtrip_preserves_type(
            self, fakereg, data, dtype):
        h, active = self._active_key()
        dhive, dsub = self._disabled_key()

        # Seed the active Run entry with its original type.
        fakereg.values[(h, active, self.RUN_NAME)] = (data, dtype)
        entry = {"type": "reg", "name": self.RUN_NAME,
                 "hive": h, "subkey": active}

        ok, msg = startup.set_startup(entry, enable=False)
        assert ok, msg
        # Disabled copy keeps (value, type); active copy is gone.
        assert fakereg.values.get((dhive, dsub, self.RUN_NAME)) == (data, dtype)
        assert (h, active, self.RUN_NAME) not in fakereg.values

        disabled_entry = {"type": "reg", "name": self.RUN_NAME,
                          "hive": dhive, "subkey": dsub}
        ok, msg = startup.set_startup(disabled_entry, enable=True)
        assert ok, msg
        # Re-enabled entry is byte-for-byte and type-identical to origin.
        assert fakereg.values.get((h, active, self.RUN_NAME)) == (data, dtype)
        assert (dhive, dsub, self.RUN_NAME) not in fakereg.values

    def test_expand_sz_regression_marker(self, fakereg):
        """Direct marker: after disabling an REG_EXPAND_SZ entry, the stored
        copy keeps the expandable type (the old code stored plain REG_SZ,
        silently killing env-var expansion for that program's launch)."""
        h, active = self._active_key()
        dhive, dsub = self._disabled_key()
        fakereg.values[(h, active, self.RUN_NAME)] = (
            self.RUN_PATH_EXPAND, fakereg.REG_EXPAND_SZ)
        entry = {"type": "reg", "name": self.RUN_NAME,
                 "hive": h, "subkey": active}

        ok, _msg = startup.set_startup(entry, enable=False)
        assert ok
        stored_value, stored_type = fakereg.values[
            (dhive, dsub, self.RUN_NAME)]
        assert stored_value == self.RUN_PATH_EXPAND
        assert stored_type == fakereg.REG_EXPAND_SZ

    def test_read_reg_value_returns_type(self, fakereg):
        h, active = self._active_key()
        fakereg.values[(h, active, "Bin")] = (b"\x01\x02",
                                              FakeRegistry.REG_BINARY)
        got = startup._read_reg_value(h, active, "Bin")
        assert got == (b"\x01\x02", FakeRegistry.REG_BINARY)

    def test_missing_value_still_reports_none(self, fakereg):
        h, active = self._active_key()
        assert startup._read_reg_value(h, active, "Ghost") is None

    def test_reenable_with_disabled_coords_restores_entry(self, fakereg):
        """Bug #5 (found while testing the type fix): entries reported by
        get_disabled_startup() carry the DISABLED key's coordinates; the
        old enable branch resolved its source via RUN_KEY_TO_DISABLED on
        those coords, fell back to the SAME key and turned re-enabling
        into a self-move whose delete step erased the entry for good."""
        h, active = self._active_key()
        dhive, dsub = self._disabled_key()

        fakereg.values[(h, active, self.RUN_NAME)] = (
            "C:\\app.exe", fakereg.REG_SZ)
        entry = {"type": "reg", "name": self.RUN_NAME,
                 "hive": h, "subkey": active}
        ok, _msg = startup.set_startup(entry, enable=False)
        assert ok

        disabled_entry = {"type": "reg", "name": self.RUN_NAME,
                          "hive": dhive, "subkey": dsub}
        ok, msg = startup.set_startup(disabled_entry, enable=True)
        assert ok, msg

        # Restored to Run AND removed from RunDisabled (never vanished).
        assert fakereg.values.get((h, active, self.RUN_NAME)) == (
            "C:\\app.exe", fakereg.REG_SZ)
        assert (dhive, dsub, self.RUN_NAME) not in fakereg.values

    def test_unmapped_pair_refused_instead_of_self_move(self, fakereg):
        """An enable request whose coords are neither a known Disabled nor
        a mapped Run pair must be REFUSED (old code would self-move)."""
        ok, msg = startup.set_startup(
            {"type": "reg", "name": "X", "hive": "HKCU",
             "subkey": r"Software\Unknown\Run"}, enable=True)
        assert not ok and "counterpart" in msg

    def test_rollback_keeps_previous_destination_type(self, fakereg):
        """Source delete fails: destination restored to ITS previous value
        AND type (not just value)."""
        h, active = self._active_key()
        dhive, dsub = self._disabled_key()

        # Destination (the disabled key) already holds a value of another type.
        fakereg.values[(dhive, dsub, self.RUN_NAME)] = (
            b"OLD-BYTES", fakereg.REG_BINARY)
        # Source (the active Run key) holds an expandable entry to move over.
        fakereg.values[(h, active, self.RUN_NAME)] = (
            self.RUN_PATH_EXPAND, fakereg.REG_EXPAND_SZ)
        fakereg.fail_delete_subkeys.add(active)  # deleting FROM Run fails

        with pytest.raises(OSError):
            startup._reg_transfer(h, active, dhive, dsub,
                                  self.RUN_NAME, self.RUN_PATH_EXPAND,
                                  fakereg.REG_EXPAND_SZ)
        # Rolled back to the previous (value, type) pair of the destination.
        assert fakereg.values[(dhive, dsub, self.RUN_NAME)] == (
            b"OLD-BYTES", fakereg.REG_BINARY)


# ---------------------------------------------------------------------------
# 3) processes.py — kill_process must be fail-closed
# ---------------------------------------------------------------------------

class TestKillProcessFailClosed:
    def test_unresolved_name_refuses_kill(self, monkeypatch):
        """Old behavior: unresolvable name -> is_protected('') False ->
        taskkill ran anyway (fail-open). Must now refuse BEFORE any call."""
        executed = []
        monkeypatch.setattr(processes, "_name_for", lambda pid: "")
        monkeypatch.setattr(processes, "run_system_cmd",
                            lambda cmd, **k: executed.append(cmd))

        ok, msg = processes.kill_process(12345)
        assert ok is False
        assert not executed, "taskkill must never run for unresolved pids"
        assert "unresolved" in msg.lower()

    def test_protected_process_refused(self, monkeypatch):
        executed = []
        monkeypatch.setattr(processes, "run_system_cmd",
                            lambda cmd, **k: executed.append(cmd))
        ok, msg = processes.kill_process(999, "EXPLORER.EXE ")
        assert ok is False
        assert not executed
        assert "protected" in msg.lower()

    def test_protected_via_resolved_name(self, monkeypatch):
        monkeypatch.setattr(processes, "_name_for", lambda pid: "lsass.exe")
        ok, msg = processes.kill_process(500)
        assert ok is False and "protected" in msg.lower()

    def test_normal_process_killed(self, monkeypatch):
        seen = {}
        # Lote F1 (S6): the kill now re-verifies the LIVE name, so the
        # fake resolver must report the same process the caller named.
        monkeypatch.setattr(processes, "_name_for", lambda pid: "notepad.exe")

        def fake_run(cmd, **k):
            seen["cmd"] = cmd
            return _CmdResult(stdout="SUCCESS: terminated", returncode=0)

        monkeypatch.setattr(processes, "run_system_cmd", fake_run)
        ok, _msg = processes.kill_process(777, "notepad.exe")
        assert ok is True
        assert seen["cmd"][0] == "taskkill"
        assert "/PID" in seen["cmd"] and "777" in seen["cmd"]

    def test_zero_pid_never_killable_when_unresolvable(self, monkeypatch):
        executed = []
        monkeypatch.setattr(processes, "_name_for", lambda pid: "")
        monkeypatch.setattr(processes, "run_system_cmd",
                            lambda cmd, **k: executed.append(cmd))
        ok, _msg = processes.kill_process(0)
        assert ok is False and not executed


# ---------------------------------------------------------------------------
# 4) utils.py — cancelled walks close every open scandir iterator
# ---------------------------------------------------------------------------

class TrackedScandir:
    """Proxies a real os.scandir iterator recording .close() calls."""

    def __init__(self, inner, registry):
        self._inner = inner
        self.registry = registry
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._inner)

    def close(self):
        if not self.closed:
            self.closed = True
            self._inner.close()


@pytest.fixture()
def nested_tree(tmp_path):
    # root/a/b/c/file.txt — first yield requires 4 simultaneously-open scanners.
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "file.txt").write_text("x")
    return tmp_path


class TestIterTreeClosesHandles:
    def test_all_handles_closed_after_cancellation(self, tmp_path,
                                                   nested_tree, monkeypatch):
        opened = []
        real_scandir = os.scandir

        def tracking(path, *a, **k):
            t = TrackedScandir(real_scandir(path, *a, **k), opened)
            opened.append(t)
            return t

        monkeypatch.setattr(os, "scandir", tracking)

        consumed = []

        def cancel_after_first():
            return len(consumed) >= 1

        gen = utils._iter_tree_files(str(nested_tree),
                                     should_cancel=cancel_after_first)
        # Draining via extend(): each yielded name flips the cancel flag so
        # the walk stops right after the first file, mid-nesting.
        consumed.extend(e.name for e in gen)
        gen.close()

        assert len(opened) > 1, (
            "nested walk should have several open scanners at cancel time")
        unclosed = [it for it in opened if not it.closed]
        assert unclosed == [], (
            f"{len(unclosed)} scandir handles leaked on cancellation")

    def test_all_handles_closed_on_normal_exhaustion(self, tmp_path,
                                                     monkeypatch):
        tree = tmp_path / "t"
        (tree / "x").mkdir(parents=True)
        (tree / "x" / "f.txt").write_text("x")

        opened = []
        real_scandir = os.scandir

        def tracking(path, *a, **k):
            t = TrackedScandir(real_scandir(path, *a, **k), opened)
            opened.append(t)
            return t

        monkeypatch.setattr(os, "scandir", tracking)

        files = list(utils._iter_tree_files(str(tree)))
        assert len(files) == 1
        assert all(it.closed for it in opened)

    def test_consumer_breaking_out_also_closes(self, tmp_path,
                                               nested_tree, monkeypatch):
        opened = []
        real_scandir = os.scandir

        def tracking(path, *a, **k):
            t = TrackedScandir(real_scandir(path, *a, **k), opened)
            opened.append(t)
            return t

        monkeypatch.setattr(os, "scandir", tracking)

        for _entry in utils._iter_tree_files(str(nested_tree)):
            break  # abandon the generator mid-walk (GeneratorExit)
        assert all(it.closed for it in opened)
