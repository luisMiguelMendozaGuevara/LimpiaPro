"""Tests del lanzador seguro de desinstaladores y de la busqueda de restos."""

import os

from limpiapro.uninstall import matches_leftover, split_command


# ------------------------------------------------------------------ split_command

def test_split_command_con_comillas_y_args(tmp_path):
    exe = tmp_path / "unin.exe"
    exe.write_bytes(b"")
    argv, err = split_command(f'"{exe}" /S /D=c:\\x')
    assert err is None
    assert argv == [str(exe), "/S", "/D=c:\\x"]


def test_split_command_resuelve_msiexec():
    argv, err = split_command("MsiExec.exe /X{11111111-2222-3333-4444-555555555555}")
    assert err is None
    assert os.path.isfile(argv[0])
    assert os.path.basename(argv[0]).lower() == "msiexec.exe"


def test_split_command_rechaza_ejecutable_inexistente():
    argv, err = split_command(r"C:\no\existe\nunca.exe /S")
    assert argv is None
    assert "no existe" in err


def test_split_command_rechaza_inyeccion_de_shell():
    # un UninstallString manipulado no debe poder colar comandos
    argv, err = split_command('inexistente.exe & calc.exe')
    assert argv is None
    assert err


def test_split_command_vacio():
    assert split_command("") == (None, "el comando de desinstalacion esta vacio")
    assert split_command(None) == (None, "el comando de desinstalacion esta vacio")


# ------------------------------------------------------------------ matches_leftover

def test_match_exacto_normalizado():
    assert matches_leftover("Mi App", "mi app")
    assert matches_leftover("Mi.App", "MI APP")


def test_todos_los_tokens_deben_aparecer():
    assert matches_leftover("Adobe Common Stuff", "Adobe Common Stuff Helper")
    assert not matches_leftover("Adobe Common Stuff", "Adobe Reader")


def test_tokens_cortos_ignorados():
    # "AI" (2 letras) no debe hacer match por si solo
    assert not matches_leftover("AI Thing", "AI Launcher")
    # "Thing" si cuenta
    assert matches_leftover("AI Thing", "Thing")
