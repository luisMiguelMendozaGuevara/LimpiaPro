"""SafetyGuard: protected user folders and their descendants never reach
deletion.

The reported incident ("LimpiaPro deleted folders related to Documents")
is exactly the class of bug these tests pin down: a *folder descendant*
of a protected user folder passed the old exact-match gate and was
rmtree'd whole. The policy now refuses:

  - drive roots and system/environment roots (exact match),
  - well-known user folders (Desktop, Documents, Downloads, Pictures,
    Music, Videos, ...) and ANY folder under them, as recursive targets,
  - targets reached *through* a junction that resolves into a protected
    area (os.path.realpath check),
while individual files anywhere (the cleanup itself, incl. winapp2 rules
under %UserProfile%\\Documents\\...) stay removable.
"""

import os
import subprocess

import pytest

from limpiapro.categories import CleanCategory
from limpiapro.safety import invalidate_safety_guard, safety_guard
from limpiapro.utils import _delete_measured, _delete_path, is_safe_delete_target, iter_file_sizes
from limpiapro.winapp2 import WinAppRule


def _make_junction(link: str, target: str) -> bool:
    """Create a junction with cmd mklink /J; False when unavailable."""
    if os.path.exists(link):
        return False
    try:
        r = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link, target],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        return r.returncode == 0
    except Exception:
        return False


@pytest.fixture(autouse=True)
def _profile_is_tmp(tmp_path, monkeypatch):
    """Point USERPROFILE at the test scratch dir so the guard's fallback
    roots land inside tmp_path, and reset the singleton after each test."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    invalidate_safety_guard()
    yield
    invalidate_safety_guard()


def test_known_user_folders_and_descendants_protected(tmp_path):
    guard = safety_guard()
    for name in ("Documents", "Desktop", "Downloads", "Pictures",
                 "Music", "Videos"):
        folder = tmp_path / name
        # The folder itself can never be a recursive target.
        assert guard.is_safe_delete_target(str(folder), is_dir=True) is False
        # Neither can any descendant folder.
        child = folder / "anything" / "deeper"
        assert guard.is_safe_delete_target(str(child), is_dir=True) is False


def test_descendant_folder_never_reaches_delete(tmp_path):
    """The reported incident: a folder under Documents is refused by the
    real deletion entry points and survives."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    folder = docs / "MyFolder"
    folder.mkdir()
    victim = folder / "file.txt"
    victim.write_text("data", encoding="utf-8")

    gone, _freed, errors = _delete_measured(str(folder))
    assert gone is False
    assert errors and errors[0].kind == "safety"
    assert folder.exists() and victim.exists()

    assert _delete_path(str(folder)) is False
    assert folder.exists() and victim.exists()


def test_category_clean_refuses_protected_descendant(tmp_path):
    """End-to-end through CleanCategory: the category lists the folder,
    the gate refuses it before any filesystem access."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    folder = docs / "Important"
    folder.mkdir()
    (folder / "keep.txt").write_text("keep", encoding="utf-8")

    cat = CleanCategory("docs", "Docs", "", [str(docs)])
    removed, errors, _freed = cat.clean()

    assert removed == 0
    assert errors >= 1
    assert (folder / "keep.txt").exists()


def test_removeself_refused_under_protected_root(tmp_path):
    """Files under Documents stay cleanable (legit winapp2 behavior), but
    REMOVESELF may never remove the folder itself."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    logs = docs / "AppLogs"
    logs.mkdir()
    (logs / "a.log").write_text("x", encoding="utf-8")

    rule = WinAppRule(root=str(logs), recurse=True,
                      patterns=("*.log",), remove_self=True)
    cat = CleanCategory("app", "App", "", [])
    cat.rules = [rule]

    removed, errors, _freed = cat.clean()
    assert removed == 1      # the file is legitimately cleaned
    assert errors >= 1       # REMOVESELF refused by the safety layer
    assert logs.exists()     # the folder under Documents survives


def test_file_inside_protected_folder_still_cleanable(tmp_path):
    """Individual files under protected folders are the cleanup itself."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    log = docs / "temp.log"
    log.write_text("log", encoding="utf-8")

    assert safety_guard().is_safe_delete_target(str(log), is_dir=False) is True
    gone, _freed, _errors = _delete_measured(str(log))
    assert gone is True
    assert not log.exists()


def test_junction_into_protected_folder_is_refused(tmp_path):
    """A junction whose target resolves inside a protected folder is never
    followed and never removed; its content stays untouched."""
    docs = tmp_path / "Documents"
    docs.mkdir()
    precious = docs / "precious.txt"
    precious.write_text("keep", encoding="utf-8")
    link = tmp_path / "link"
    if not _make_junction(str(link), str(docs)):
        pytest.skip("junctions are unavailable")

    # The junction itself resolves into Documents: refused as a target.
    assert safety_guard().is_safe_delete_target(str(link), is_dir=True) is False
    gone, _freed, errors = _delete_measured(str(link))
    assert gone is False
    assert errors and errors[0].kind == "safety"
    assert precious.exists()

    # A file reached THROUGH the junction is refused too (literal path
    # looks harmless, real path lives inside Documents).
    through = os.path.join(str(link), "precious.txt")
    assert safety_guard().is_safe_delete_target(through, is_dir=False) is False
    gone2, _freed2, _errors2 = _delete_measured(through)
    assert gone2 is False
    assert precious.exists()


def test_safe_junction_removed_as_link_only(tmp_path):
    """A junction that resolves outside protected areas is still cleanable,
    but only the link is removed — never its target's contents."""
    target = tmp_path / "cache_target"
    target.mkdir()
    (target / "data.bin").write_bytes(b"x" * 64)
    link = tmp_path / "cachelink"
    if not _make_junction(str(link), str(target)):
        pytest.skip("junctions are unavailable")

    gone, _freed, _errors = _delete_measured(str(link))
    assert gone is True
    assert (target / "data.bin").exists()


def test_rule_walk_does_not_descend_junctions(tmp_path):
    """os.walk descends into junctions even with followlinks=False; the
    category walk must prune them so targets never come from outside the
    rule's physical tree."""
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "target"   # NOT under the rule root
    target.mkdir()
    (target / "jfile.bin").write_bytes(b"j")
    link = root / "jlink"
    if not _make_junction(str(link), str(target)):
        pytest.skip("junctions are unavailable")

    rule = WinAppRule(root=str(root), recurse=True, patterns=("*.bin",))
    cat = CleanCategory("j", "J", "", [])
    cat.rules = [rule]

    targets = list(cat._iter_targets())
    assert not any(str(link) in path for _r, path in targets)
    _removed, errors, _freed = cat.clean()
    assert (target / "jfile.bin").exists()
    assert errors == 0


def test_iter_file_sizes_does_not_descend_junctions(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "big.bin").write_bytes(b"x" * 100)
    link = tmp_path / "link"
    if not _make_junction(str(link), str(target)):
        pytest.skip("junctions are unavailable")

    files = list(iter_file_sizes(str(tmp_path)))
    assert not any("link" in path for path, _size in files)


def test_backward_compat_exact_roots():
    """The historical utils.is_safe_delete_target contract is unchanged."""
    assert is_safe_delete_target("C:\\") is False
    assert is_safe_delete_target("D:\\") is False
    assert is_safe_delete_target(r"C:\Windows") is False
    assert is_safe_delete_target(r"C:\Windows\System32") is False
    assert is_safe_delete_target(r"C:\Program Files") is False
    assert is_safe_delete_target(r"C:\Program Files (x86)") is False


def test_tmp_children_still_allowed(tmp_path):
    """Ordinary scratch folders (not under any protected user folder)
    remain cleanable, as before."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    assert safety_guard().is_safe_delete_target(str(scratch), is_dir=True) is True
    assert safety_guard().is_safe_delete_target(
        str(scratch / "sub"), is_dir=True) is True
