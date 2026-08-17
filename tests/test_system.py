"""Tests for the console-command helper (OEM encoding)."""

import subprocess

from limpiapro.utils import _oem_cp, run_system_cmd


def test_oem_cp_returns_cp_string():
    cp = _oem_cp()
    assert isinstance(cp, str)
    assert cp.isdigit()


def test_oem_cp_fallback_on_error(monkeypatch):
    class _NoCP:
        def GetOEMCP(self):
            raise OSError("no windows")

    monkeypatch.setattr("limpiapro.utils.ctypes.windll.kernel32", _NoCP())
    assert _oem_cp() == "850"


def test_run_system_cmd_decodes_oem_without_mojibake(monkeypatch):
    """When the command emits cp850 with accents, the output must come
    back without mojibake."""
    calls = {}

    def fake_run(args, **kw):
        calls["args"] = args
        calls["kw"] = kw
        raw = "Tareas con acentos: á é í ó ú ñ".encode("cp850")
        text = raw.decode(kw["encoding"], errors="replace")
        return subprocess.CompletedProcess(args, 0, stdout=text, stderr="")

    monkeypatch.setattr("limpiapro.utils.subprocess.run", fake_run)
    monkeypatch.setattr("limpiapro.utils._oem_cp", lambda: "850")

    res = run_system_cmd(["schtasks", "/query"])
    assert res.returncode == 0
    assert "Tareas con acentos: á é í ó ú ñ" == res.stdout
    assert calls["kw"]["encoding"] == "cp850"
    assert calls["args"] == ["schtasks", "/query"]


def test_run_system_cmd_passes_safe_creationflags(monkeypatch):
    calls = {}

    def fake_run(args, **kw):
        calls["kw"] = kw
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("limpiapro.utils.subprocess.run", fake_run)
    monkeypatch.setattr("limpiapro.utils._oem_cp", lambda: "850")
    run_system_cmd(["whoami"])
    assert calls["kw"]["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert calls["kw"]["capture_output"] is True
    assert calls["kw"]["text"] is True
