"""B2 regressions: optional recycle-bin cleanup (move instead of delete).

Settings carry the user opt-in (delete_to_recycle_bin, default False =
legacy permanent delete). The core honors it through
utils._delete_measured(to_recycle=True) / _delete_path(to_recycle=True):

* the SafetyGuard gate runs FIRST (recycling a guarded path is still a
  guarded path),
* a successful move reports the path as gone and its size as freed,
* a failed move (bin disabled, backend missing, unsupported volume)
  leaves the target untouched and reports a structured "recycle" error
  - never a destructive fallback.
"""

from __future__ import annotations

import os
import shutil

import pytest

from limpiapro import utils
from limpiapro.settings import Settings

# ------------------------------------------------------------------ settings


def test_delete_to_recycle_bin_defaults_to_false():
    s = Settings()
    assert s.delete_to_recycle_bin is False


def test_delete_to_recycle_bin_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    s = Settings()
    s.delete_to_recycle_bin = True
    s.save(path)

    loaded = Settings.load(path)
    assert loaded.delete_to_recycle_bin is True


def test_delete_to_recycle_bin_rejects_wrong_type(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"delete_to_recycle_bin": "yes"}', encoding="utf-8")

    assert Settings.load(path).delete_to_recycle_bin is False


# ------------------------------------------------------------------- helpers


@pytest.fixture()
def fake_bin(tmp_path, monkeypatch):
    """Replace send2trash with a move-to-folder fake; records calls."""
    bin_dir = tmp_path / "fake_recycle_bin"
    bin_dir.mkdir()
    calls = []

    def _send2trash(path):
        calls.append(str(path))
        # Real send2trash moves the whole entry into the bin.
        shutil.move(path, bin_dir / os.path.basename(str(path)))

    monkeypatch.setattr(utils, "_send2trash", _send2trash)
    return calls


def test_recycled_file_is_gone_and_measured(tmp_path, fake_bin):
    f = tmp_path / "junk.log"
    f.write_bytes(b"x" * 2048)

    ok, freed, errors = utils._delete_measured(str(f), to_recycle=True)

    assert (ok, errors) == (True, [])
    assert freed == 2048
    assert not f.exists()
    assert fake_bin == [str(f)]


def test_recycled_tree_is_gone_and_measured(tmp_path, fake_bin):
    d = tmp_path / "cache-tree"
    (d / "sub").mkdir(parents=True)
    (d / "a.bin").write_bytes(b"a" * 100)
    (d / "sub" / "b.bin").write_bytes(b"b" * 300)

    ok, freed, errors = utils._delete_measured(str(d), to_recycle=True)

    assert (ok, errors) == (True, [])
    assert freed == 400
    assert not d.exists()
    assert len(fake_bin) == 1


def test_recycle_mode_still_respects_safety_gate(tmp_path, monkeypatch,
                                                 fake_bin):
    # Simulate the gate refusing the target (kept platform-independent:
    # which paths are guarded is safety.py's own test suite's job).
    monkeypatch.setattr(utils, "is_safe_delete_target",
                        lambda *_a, **_k: False)
    f = tmp_path / "guarded.log"
    f.write_text("data")

    ok, freed, errors = utils._delete_measured(str(f), to_recycle=True)

    assert ok is False
    assert freed == 0
    assert [e.kind for e in errors] == ["safety"]
    assert f.exists()                # untouched
    assert fake_bin == []            # never handed to the bin


def test_failed_recycle_leaves_target_untouched(tmp_path, monkeypatch):
    def broken_send2trash(_path):
        raise OSError("recycle bin is disabled")

    monkeypatch.setattr(utils, "_send2trash", broken_send2trash)
    f = tmp_path / "precious.txt"
    f.write_text("keep me")

    ok, _freed, errors = utils._delete_measured(str(f), to_recycle=True)

    assert ok is False
    assert [e.kind for e in errors] == ["recycle"]
    assert f.read_text() == "keep me"   # fail-safe, not deleted


def test_missing_backend_reports_error_instead_of_crashing(
        tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "_send2trash", None)
    f = tmp_path / "x.txt"
    f.write_text("x")

    ok, _freed, errors = utils._delete_measured(str(f), to_recycle=True)

    assert ok is False
    assert errors and errors[0].kind == "recycle"
    assert "backend" in errors[0].message
    assert f.exists()


def test_default_mode_never_touches_the_bin(tmp_path, monkeypatch):
    def _must_not_be_called(_path):
        raise AssertionError("permanent delete must not use send2trash")

    monkeypatch.setattr(utils, "_send2trash", _must_not_be_called)
    f = tmp_path / "plain.txt"
    f.write_text("x")

    ok, freed, errors = utils._delete_measured(str(f))

    assert (ok, errors) == (True, [])
    assert freed == 1
    assert not f.exists()


def test_delete_path_honors_recycle_flag(tmp_path, fake_bin):
    f = tmp_path / "dupe.bin"
    f.write_bytes(b"z" * 16)

    assert utils._delete_path(str(f), to_recycle=True) is True
    assert not f.exists()
    assert fake_bin == [str(f)]


# --------------------------------------------------------------- i18n keys

def test_confirmation_note_appears_only_in_recycle_mode():
    from limpiapro.i18n import t
    from limpiapro.ui.messages import clean_confirmation

    class Cat:
        key = "temp"
        label = "Temp"
        size = 10
        recycle_bin = False
        needs_admin = False

    base = clean_confirmation([Cat()])
    recycled = clean_confirmation([Cat()], to_recycle=True)

    # Legacy output unchanged; recycle mode appends exactly one note.
    assert len(recycled[3]) == len(base[3]) + 1
    assert recycled[3][-1] == t("msg.clean_note_to_recycle")


# ------------------------------------------------- startup status helper

def test_humanize_duration():
    # Lives in utils (Qt-free) so it is testable on any platform.
    assert utils.humanize_duration(0) == "<1 min"
    assert utils.humanize_duration(59) == "<1 min"
    assert utils.humanize_duration(300) == "5 min"
    assert utils.humanize_duration(7200) == "2 h"
