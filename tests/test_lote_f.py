"""Tests for Lote F1: security — S1 uninstaller risk, S5 sibling-profile
redaction, S6 kill TOCTOU re-verification."""

from limpiapro import processes, uninstall, utils

# ---------------------------------------------------------------- S1


def _mk_exe(directory, name="evil.exe"):
    directory.mkdir(parents=True, exist_ok=True)
    exe = directory / name
    exe.write_bytes(b"MZ")
    return exe


def test_uninstall_risk_temp(monkeypatch, tmp_path):
    temp = tmp_path / "temp"
    exe = _mk_exe(temp)
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.delenv("TMP", raising=False)
    cmd = f'"{exe}" /S'
    assert uninstall.uninstall_risk(cmd) == "temp"
    ok, msg = uninstall.launch_uninstaller(cmd)
    assert ok is False and "refused" in msg.lower()


def test_uninstall_risk_user_profile(monkeypatch, tmp_path):
    profile = tmp_path / "Users" / "juan"
    exe = _mk_exe(profile / "AppData" / "Local" / "App")
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.setenv("HOME", str(profile))
    monkeypatch.setenv("USERPROFILE", str(profile))
    assert uninstall.uninstall_risk(f'"{exe}" /S') == "user"


def test_uninstall_risk_system_location(monkeypatch, tmp_path):
    prog = tmp_path / "Program Files" / "App"
    exe = _mk_exe(prog)
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.delenv("TMP", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "Users" / "juan"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "Users" / "juan"))
    assert uninstall.uninstall_risk(f'"{exe}" /S') == "system"


def test_launch_never_invokes_popen_for_temp_exe(monkeypatch, tmp_path):
    temp = tmp_path / "temp"
    exe = _mk_exe(temp)
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.delenv("TMP", raising=False)

    def boom(*_a, **_k):
        raise AssertionError("Popen must not run for temp-dir uninstallers")

    monkeypatch.setattr(uninstall.subprocess, "Popen", boom)
    ok, _msg = uninstall.launch_uninstaller(f'"{exe}" /S')
    assert ok is False


# ---------------------------------------------------------------- S5


def test_redact_masks_sibling_profiles(monkeypatch, tmp_path):
    fake_home = tmp_path / "Users" / "juan"
    fake_home.mkdir(parents=True)
    ana = tmp_path / "Users" / "ana"
    monkeypatch.setattr(utils.os.path, "expanduser",
                        lambda _p: str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))

    out = utils.redact_user_paths(
        f"deleted {fake_home}/cache and {ana}/misc")
    assert str(fake_home) not in out and str(ana) not in out
    assert "~/cache" in out and "~ana/misc" in out


def test_redact_sibling_masking_has_no_prefix_mangling(monkeypatch, tmp_path):
    fake_home = tmp_path / "Users" / "juan"
    fake_home.mkdir(parents=True)
    juanetico = tmp_path / "Users" / "juanetico"
    monkeypatch.setattr(utils.os.path, "expanduser",
                        lambda _p: str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))

    # The boundary rule must survive: "juanetico" is a DIFFERENT profile
    # and gets its OWN mask token, not a corrupted match of "juan".
    out = utils.redact_user_paths(f"{juanetico}/logs")
    assert out == "~juanetico/logs"


def test_redact_ignores_non_users_roots(monkeypatch, tmp_path):
    fake_home = tmp_path / "data" / "juan"
    fake_home.mkdir(parents=True)
    monkeypatch.setattr(utils.os.path, "expanduser",
                        lambda _p: str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))
    monkeypatch.setenv("HOME", str(fake_home))

    # users-root is "data": the generic sibling pass must NOT fire, or a
    # redirected-profile layout would mask half the filesystem.
    other = tmp_path / "data" / "ana"
    out = utils.redact_user_paths(f"see {other}/file")
    assert out == f"see {other}/file"


# ---------------------------------------------------------------- S6


def test_kill_refuses_when_live_name_differs(monkeypatch):
    executed = []
    monkeypatch.setattr(processes, "run_system_cmd",
                        lambda cmd, **k: executed.append(cmd))
    # Snapshot said notepad.exe, the live PID now resolves to other.exe:
    # a recycled PID — the kill must not proceed.
    monkeypatch.setattr(processes, "_name_for", lambda pid: "other.exe")
    ok, msg = processes.kill_process(777, "notepad.exe")
    assert ok is False
    assert not executed, "taskkill must never run for a recycled PID"
    assert "now resolves" in msg


def test_kill_accepts_extensionless_caller_name(monkeypatch):
    seen = {}

    def fake_run(cmd, **k):
        seen["cmd"] = cmd
        return type("R", (), {"stdout": "OK", "stderr": "",
                              "returncode": 0})()

    monkeypatch.setattr(processes, "run_system_cmd", fake_run)
    monkeypatch.setattr(processes, "_name_for", lambda pid: "notepad.exe")
    ok, _msg = processes.kill_process(777, "notepad")
    assert ok is True and seen["cmd"][0] == "taskkill"


def test_kill_refuses_when_process_exited_before_kill(monkeypatch):
    executed = []
    monkeypatch.setattr(processes, "run_system_cmd",
                        lambda cmd, **k: executed.append(cmd))
    monkeypatch.setattr(processes, "_name_for", lambda pid: "")
    ok, msg = processes.kill_process(777, "notepad.exe")
    assert ok is False and not executed
    assert "nothing" in msg
