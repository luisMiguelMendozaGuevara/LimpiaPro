"""Tests del helper de comandos de consola (codificacion OEM)."""

import subprocess

import pytest

from limpiapro.utils import _oem_cp, run_system_cmd


def test_oem_cp_devuelve_cadena_cp():
    cp = _oem_cp()
    assert isinstance(cp, str)
    assert cp.isdigit()


def test_oem_cp_fallback_ante_error(monkeypatch):
    class _SinCP:
        def GetOEMCP(self):
            raise OSError("no windows")

    monkeypatch.setattr("limpiapro.utils.ctypes.windll.kernel32", _SinCP())
    assert _oem_cp() == "850"


def test_run_system_cmd_decodifica_oem_sin_mojibake(monkeypatch):
    """Si el comando emite cp850 con acentos, la salida sale sin mojibake."""
    llamadas = {}

    def fake_run(args, **kw):
        llamadas["args"] = args
        llamadas["kw"] = kw
        raw = "Tareas con acentos: á é í ó ú ñ".encode("cp850")
        text = raw.decode(kw["encoding"], errors="replace")
        return subprocess.CompletedProcess(args, 0, stdout=text, stderr="")

    monkeypatch.setattr("limpiapro.utils.subprocess.run", fake_run)
    monkeypatch.setattr("limpiapro.utils._oem_cp", lambda: "850")

    res = run_system_cmd(["schtasks", "/query"])
    assert res.returncode == 0
    assert "Tareas con acentos: á é í ó ú ñ" == res.stdout
    assert llamadas["kw"]["encoding"] == "cp850"
    assert llamadas["args"] == ["schtasks", "/query"]


def test_run_system_cmd_pasa_creationflags_seguro(monkeypatch):
    llamadas = {}

    def fake_run(args, **kw):
        llamadas["kw"] = kw
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("limpiapro.utils.subprocess.run", fake_run)
    monkeypatch.setattr("limpiapro.utils._oem_cp", lambda: "850")
    run_system_cmd(["whoami"])
    assert llamadas["kw"]["creationflags"] == subprocess.CREATE_NO_WINDOW
    assert llamadas["kw"]["capture_output"] is True
    assert llamadas["kw"]["text"] is True