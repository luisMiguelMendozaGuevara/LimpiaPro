"""Tests for Lote E1: compatibility, dead code removal and metadata.

E1.1 junction compatibility: os.path.isjunction() is Python 3.12+, but
pyproject promises >=3.10, so every check must go through utils.is_junction
(native on 3.12+, reparse-tag fallback on 3.10/3.11 Windows, always-False
on POSIX). E1.2 keeps pyproject's version in sync with APP_VERSION. E1.4
guards the removed dead code stays removed. E1.6 keeps the CI matrix
covering the promised Python floor.
"""

import os
import re
from pathlib import Path

import pytest

from limpiapro import APP_VERSION, utils

REPO = Path(__file__).resolve().parent.parent

# Windows reparse tags (public constants from the win32 API).
IO_REPARSE_TAG_MOUNT_POINT = 0xA000_0003
IO_REPARSE_TAG_SYMLINK = 0xA000_000C


# ---------------------------------------------------------------- E1.1


class _FakeStat:
    def __init__(self, reparse_tag=0):
        self.st_reparse_tag = reparse_tag


def test_is_junction_regular_paths_are_false(tmp_path):
    """Native semantics on the running interpreter: files, dirs, symlinks
    and missing paths are never junctions."""
    f = tmp_path / "file.txt"
    f.write_bytes(b"x")
    d = tmp_path / "dir"
    d.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(f, link)
    except OSError as e:
        # Windows without Developer Mode / Privilege (WinError 1314) cannot
        # create symlinks; the junction shim is still correct — skip the
        # symlink part of the test on such hosts.
        if getattr(e, "winerror", None) == 1314:
            pytest.skip("symlink creation requires privilege (WinError 1314)")
        raise
    broken = tmp_path / "broken"
    try:
        os.symlink(tmp_path / "absent_target", broken)
    except OSError as e:
        if getattr(e, "winerror", None) == 1314:
            pytest.skip("symlink creation requires privilege (WinError 1314)")
        raise

    assert utils.is_junction(str(f)) is False
    assert utils.is_junction(str(d)) is False
    assert utils.is_junction(str(link)) is False
    assert utils.is_junction(str(broken)) is False
    assert utils.is_junction(str(tmp_path / "absent")) is False


def test_reparse_fallback_detects_mount_point(monkeypatch):
    """3.10/3.11 Windows fallback: a non-following stat exposing the
    MOUNT_POINT tag means junction (broken junctions included: the
    reparse point itself stats fine with follow_symlinks=False)."""
    seen = {}

    def fake_stat(path, *, follow_symlinks):
        seen["follow_symlinks"] = follow_symlinks
        return _FakeStat(IO_REPARSE_TAG_MOUNT_POINT)

    monkeypatch.setattr(utils.os, "stat", fake_stat)
    assert utils._isjunction_reparse("C:\\Some\\Junction") is True
    assert seen["follow_symlinks"] is False


def test_reparse_fallback_rejects_symlink_tag(monkeypatch):
    """A symlink reparse tag is NOT a junction: islink() handles symlinks
    separately at every call site, and the fallback must not conflate
    them (isjunction() is mount-point-only on 3.12+)."""

    def fake_stat(path, *, follow_symlinks):
        return _FakeStat(IO_REPARSE_TAG_SYMLINK)

    monkeypatch.setattr(utils.os, "stat", fake_stat)
    assert utils._isjunction_reparse("C:\\Some\\Link") is False


def test_reparse_fallback_no_tag_and_oserror(monkeypatch):
    def fake_stat(path, *, follow_symlinks):
        return _FakeStat(0)

    monkeypatch.setattr(utils.os, "stat", fake_stat)
    assert utils._isjunction_reparse("C:\\plain") is False

    def raising_stat(path, *, follow_symlinks):
        raise FileNotFoundError(path)

    monkeypatch.setattr(utils.os, "stat", raising_stat)
    assert utils._isjunction_reparse("C:\\absent") is False


def test_isjunction_only_referenced_inside_the_shim():
    """Guard: no call site may use os.path.isjunction directly — on
    Python 3.10/3.11 the attribute does not exist and the delete/scan
    core would crash with AttributeError (the E1.1 regression). Only the
    shim module itself may reference it."""
    offenders = []
    for py in (REPO / "limpiapro").rglob("*.py"):
        rel = py.relative_to(REPO).as_posix()
        if rel == "limpiapro/utils.py":
            continue  # the shim itself
        text = py.read_text(encoding="utf-8")
        for n, line in enumerate(text.splitlines(), 1):
            if "os.path.isjunction" in line:
                offenders.append(f"{rel}:{n}")
    assert offenders == [], (
        f"usos directos de os.path.isjunction fuera del shim: {offenders}")


# ---------------------------------------------------------------- E1.2


def test_pyproject_version_matches_app_version():
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m, "pyproject.toml sin campo version"
    assert m.group(1) == APP_VERSION


# ---------------------------------------------------------------- E1.4


def test_dead_code_stays_dead():
    """Guards for the E1.3/E1.4 removals: the dead service, the legacy
    dialog, the compatibility shim and the unused constant must not come
    back (nothing references them anymore)."""
    self_path = Path(__file__).resolve()
    forbidden = ["CleanupService", "confirm_destructive",
                 "PROGRESS_RULES", "ui.widgets"]
    offenders: list[str] = []
    for base in ("limpiapro", "tests"):
        for py in (REPO / base).rglob("*.py"):
            if py.resolve() == self_path:
                continue  # this guard file lists the needles itself
            text = py.read_text(encoding="utf-8")
            offenders.extend(
                f"{py.relative_to(REPO)}: {needle}"
                for needle in forbidden if needle in text)
    assert offenders == [], f"código muerto re-introducido: {offenders}"


# ---------------------------------------------------------------- E1.6


def test_ci_matrix_covers_promised_python_floor():
    """requires-python >=3.10 must be exercised by CI: the test job matrix
    has to include 3.10 and 3.11 (text check, no PyYAML dependency)."""
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    m = re.search(r"python-version:\s*\[[^\]]*\]", ci)
    assert m, "no matrix found in ci.yml test job"
    versions = [v.strip('"') for v in re.findall(r'"(3\.\d+)"', m.group(0))]
    assert "3.10" in versions, "CI no prueba 3.10 (prometido por requires-python)"
    assert "3.11" in versions, "CI no prueba 3.11 (prometido por requires-python)"


# ---------------------------------------------------- integration sanity


def test_delete_paths_still_function_with_the_shim(tmp_path, monkeypatch):
    """End-to-end sanity: _delete_measured and _delete_path keep working
    through the abstraction on the running interpreter."""
    f = tmp_path / "junk.tmp"
    f.write_bytes(b"x" * 10)
    ok, freed, errors = utils._delete_measured(str(f))
    assert ok and freed == 10 and errors == []

    d = tmp_path / "sub"
    d.mkdir()
    (d / "a.log").write_bytes(b"y" * 3)
    assert utils._delete_path(str(d)) is True
    assert not d.exists()


@pytest.mark.parametrize("attr", ["is_junction", "_isjunction_reparse"])
def test_shim_symbols_exist(attr):
    assert hasattr(utils, attr)
