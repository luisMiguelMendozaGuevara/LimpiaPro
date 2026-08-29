"""Batch-A hardening regressions.

Covers the security/hygiene round applied on top of the P0 fixes:

S7 - dependency pins must stay EXACT (==): a float pin silently let
     untested upstream releases change shipped, compiled behavior.
S8 - least-privilege CI: workflows declare `permissions: contents: read`
     and keep an intact `[main]` push trigger.
S2 - log hygiene in audit_log/utils:
     * redact_user_paths() masks the user home before serialization,
       case-insensitively, with prefix-boundary safety and support for
       literal %USERPROFILE% tokens.
     * _rotate_log_file() shifts generations (.1/.2) once a size cap is
       reached so logs can never grow unbounded.
     * AuditLogger serializes appends with a lock (well-formed JSONL
       under concurrent QThread workers) and honors per-instance caps.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

import pytest

from limpiapro import audit_log, utils

REPO_ROOT = Path(__file__).resolve().parents[1]
WF_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


# ---------------------------------------------------------------- S7 pins

@pytest.mark.parametrize("req_file",
                         ["requirements.txt", "requirements-dev.txt"])
def test_dependency_specs_are_exact(req_file):
    """Every requirement line must be a hard == pin (no floats)."""
    raw = (REPO_ROOT / req_file).read_text(encoding="utf-8")
    specs = [line.strip() for line in raw.splitlines()
             if line.strip() and not line.strip().startswith("#")]
    assert specs, f"{req_file} unexpectedly empty"
    for spec in specs:
        assert re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][A-Za-z0-9.\-]*", spec), \
            f"{req_file}: not an exact pin -> {spec!r}"


# ------------------------------------------------------------- S8 CI hardening

def test_ci_workflow_declares_least_privilege_token():
    text = WF_PATH.read_text(encoding="utf-8")
    assert re.search(r"^permissions:\s*\n\s*contents:\s*read\s*$", text, re.M)


def test_ci_workflow_push_trigger_stays_intact():
    # Byte-level guard against display/copy corruption of the YAML flow
    # sequence ([main]); mangled variants would disable push validation.
    text = WF_PATH.read_text(encoding="utf-8")
    assert re.search(r"branches:\s*\[main\]", text)


# -------------------------------------------- S2a redact_user_paths()

@pytest.fixture()
def fake_home(monkeypatch, tmp_path) -> str:
    home = tmp_path / "homeland"
    home.mkdir()
    monkeypatch.setattr(os.path, "expanduser", lambda _arg: str(home))
    return str(home)


def test_redact_masks_exact_home(fake_home):
    target = os.path.join(fake_home, "App", "Cache", "data_0")
    expected = os.path.join("~", "App", "Cache", "data_0")
    assert utils.redact_user_paths(target) == expected


def test_redact_case_insensitive(fake_home):
    weird_casing = fake_home.upper()
    out = utils.redact_user_paths(os.path.join(weird_casing, "x", "y"))
    assert out.startswith("~"), out


def test_redact_needs_boundary(fake_home, monkeypatch):
    # A sibling home sharing the prefix ("homelandby") must NOT be masked.
    # Isolate from the real environment: on machines where %TEMP% lives under
    # the actual USERPROFILE/HOME, the sibling path is still inside the real
    # home, so its prefix WOULD legitimately be masked. Only the fake home
    # should act as a needle here.
    monkeypatch.delenv("USERPROFILE", raising=False)
    monkeypatch.delenv("HOME", raising=False)
    sibling = fake_home + "by"
    out = utils.redact_user_paths(os.path.join(sibling, "f"))
    assert out == os.path.join(sibling, "f")


def test_redact_literal_userprofile_token(monkeypatch):
    monkeypatch.setenv("HOME", "")
    monkeypatch.setenv("USERPROFILE", "")
    monkeypatch.setattr(os.path, "expanduser", lambda _arg: "~")
    out = utils.redact_user_paths("%USERPROFILE%" + "\\Chrome\\Cookies")
    assert out == "~\\Chrome\\Cookies"


def test_redact_noop_on_empty():
    assert utils.redact_user_paths("") == ""


# -------------------------------------------- S2b rotation primitive

def test_rotate_shifts_generations(tmp_path):
    live = tmp_path / "app.log"
    gen1 = tmp_path / "app.log.1"
    gen2 = tmp_path / "app.log.2"
    live.write_text("L" * 50)
    gen1.write_text("A" * 10)
    gen2.write_text("B" * 5)
    utils._rotate_log_file(str(live), max_bytes=40, backups=2)
    assert gen2.read_text() == "A" * 10   # old .1 promoted to .2
    assert gen1.read_text() == "L" * 50   # live file became .1
    assert not live.exists()


def test_rotate_skips_below_threshold(tmp_path):
    live = tmp_path / "small.log"
    live.write_text("tiny")
    utils._rotate_log_file(str(live), max_bytes=1000, backups=2)
    assert live.exists()
    assert not (tmp_path / "small.log.1").exists()


def test_rotate_missing_file_is_silent(tmp_path):
    # Must never raise even when there is nothing to rotate.
    utils._rotate_log_file(str(tmp_path / "ghost.log"),
                           max_bytes=1, backups=1)


# ---------------------------------------- S2c errlog integration

def test_errlog_rotates_then_redacts(tmp_path, monkeypatch, fake_home):
    monkeypatch.setattr(utils, "get_logs_dir", lambda: str(tmp_path))
    seed = tmp_path / "limpiapro_error.log"
    seed.write_text("z" * utils._ERRLOG_MAX_BYTES)

    secret = os.path.join(fake_home, "Chrome", "Cookies")
    utils._errlog(f"failed to remove {secret}", component="t")

    rotated = tmp_path / "limpiapro_error.log.1"
    assert rotated.exists(), "oversized error log must rotate on next write"
    record = json.loads(
        (tmp_path / "limpiapro_error.log").read_text().strip())
    assert record["msg"] == f"failed to remove {os.path.join('~', 'Chrome', 'Cookies')}"


# ---------------------------------------- S2d AuditLogger behaviors

def _logger(tmp_path: Path, **kwargs) -> audit_log.AuditLogger:
    lg = audit_log.AuditLogger(**kwargs)
    lg._log_path = tmp_path / "audit.jsonl"
    return lg


def test_audit_concurrent_writes_are_whole_lines(tmp_path):
    logger = _logger(tmp_path, max_bytes=100 * 1024 * 1024)
    n_threads, n_ops = 8, 25

    def worker(tag: int) -> None:
        for i in range(n_ops):
            logger.log_operation(operation="cleanup", category="cat",
                                 action="delete", path=f"/t{tag}/f{i}")

    threads = [threading.Thread(target=worker, args=(t,))
               for t in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    lines = (tmp_path / "audit.jsonl").read_text().splitlines()
    assert len(lines) == n_threads * n_ops
    records = [json.loads(line) for line in lines]  # every line well-formed
    assert len({r["path"] for r in records}) == n_threads * n_ops


def test_audit_rotation_keeps_bounded(tmp_path):
    logger = _logger(tmp_path, max_bytes=300, backups=1)
    filler = "y" * 60
    for i in range(4):
        logger.log_operation(operation="scan", category="c", action="detect",
                             path=f"/p/{i}/{filler}")
    assert (tmp_path / "audit.jsonl.1").exists(), \
        "audit log must rotate at its per-instance cap"


def test_audit_records_mask_home_everywhere(tmp_path, fake_home):
    logger = _logger(tmp_path)
    logger.log_operation(
        operation="cleanup", category="chrome", action="delete",
        path=os.path.join(fake_home, "Chrome", "cache.bin"),
        error_msg=f"EACCES {os.path.join(fake_home, 'lock')}",
        details={"src": os.path.join(fake_home, "src"), "keep": 7})
    rec = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert rec["path"] == os.path.join("~", "Chrome", "cache.bin")
    assert rec["error_msg"] == f"EACCES {os.path.join('~', 'lock')}"
    assert rec["details"]["src"] == os.path.join("~", "src")
    assert rec["details"]["keep"] == 7          # non-str detail untouched


# --------------------------------------------- B4 release artifact integrity

def test_ci_build_generates_sha256_checksums():
    """The build job must publish a SHA256 sidecar for the exe so users
    (and AV triage) can verify the artifact without re-downloading it."""
    text = WF_PATH.read_text(encoding="utf-8")
    assert "Get-FileHash" in text, "build job lacks a SHA256 hashing step"
    assert ".sha256" in text, "checksum sidecar is not uploaded"
    # The sidecar must travel with the artifact, not stay on the runner.
    upload = text.split("Upload executable", 1)[1]
    assert "LimpiaPro.exe.sha256" in upload
