"""Tests for the safe uninstaller launcher and the leftover search."""

import os

from limpiapro.uninstall import _registry_target_allowed, matches_leftover, split_command

# ------------------------------------------------------------------ split_command

def test_split_command_with_quotes_and_args(tmp_path):
    exe = tmp_path / "unin.exe"
    exe.write_bytes(b"")
    argv, err = split_command(f'"{exe}" /S /D=c:\\x')
    assert err is None
    assert argv == [str(exe), "/S", "/D=c:\\x"]


def test_split_command_resolves_msiexec():
    argv, err = split_command("MsiExec.exe /X{11111111-2222-3333-4444-555555555555}")
    assert err is None
    assert os.path.isfile(argv[0])
    assert os.path.basename(argv[0]).lower() == "msiexec.exe"


def test_split_command_rejects_missing_executable():
    argv, err = split_command(r"C:\does\not\exist.exe /S")
    assert argv is None
    assert "does not exist" in err


def test_split_command_rejects_shell_injection():
    # a tampered UninstallString must not be able to smuggle commands
    argv, err = split_command('missing.exe & calc.exe')
    assert argv is None
    assert err


def test_split_command_empty():
    assert split_command("") == (None, "the uninstall command is empty")
    assert split_command(None) == (None, "the uninstall command is empty")


# ------------------------------------------------------------------ matches_leftover

def test_normalized_exact_match():
    assert matches_leftover("Mi App", "mi app")
    assert matches_leftover("Mi.App", "MI APP")


def test_all_tokens_must_appear():
    assert matches_leftover("Adobe Common Stuff", "Adobe Common Stuff Helper")
    assert not matches_leftover("Adobe Common Stuff", "Adobe Reader")


def test_short_tokens_ignored():
    # "AI" (2 letters) must not match on its own
    assert not matches_leftover("AI Thing", "AI Launcher")
    # "Thing" does count
    assert matches_leftover("AI Thing", "Thing")


# ------------------------------------------------------------------ registry safety

def test_registry_target_requires_software_root():
    assert _registry_target_allowed(r"Software\MyApp") is True
    assert _registry_target_allowed(r"Software\Wow6432Node\MyApp") is True
    assert _registry_target_allowed(r"Software") is False
    assert _registry_target_allowed("") is False


def test_registry_target_refuses_blocked_namespaces():
    assert _registry_target_allowed(r"Software\Microsoft\Office") is False
    assert _registry_target_allowed(r"Software\Classes") is False
    assert _registry_target_allowed(r"Software\Policies\Foo") is False
    assert _registry_target_allowed(r"Software\Wow6432Node\Microsoft\X") is False


def test_registry_target_refuses_non_software():
    assert _registry_target_allowed(r"Classes\MyApp") is False
    assert _registry_target_allowed(r"Policies\Foo") is False


def test_delete_registry_path_rejects_unsafe_paths():
    from limpiapro.uninstall import delete_registry_path
    # Never allowed, so it must not touch the registry at all.
    assert delete_registry_path(r"HKLM\Software\Microsoft\Windows") is False
    assert delete_registry_path(r"HKCU\Software") is False
    assert delete_registry_path(r"HKLM\Classes\Foo") is False
    assert delete_registry_path("") is False
