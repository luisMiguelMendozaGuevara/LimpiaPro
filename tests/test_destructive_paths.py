"""Hostile filesystem cases for destructive cleanup operations."""

import os
import stat
import subprocess

import pytest

from limpiapro.categories import CleanCategory


def _make_junction(link, target) -> bool:
    """Create an NTFS junction (works without administrator rights)."""
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                            capture_output=True, text=True)
    return result.returncode == 0


def test_junction_location_is_removed_as_link_only(tmp_path):
    """A cleanup location that IS a reparse point must never be traversed:
    the link is removed, its target's contents survive.

    Regression: _iter_targets listed `link/<child>` through the junction,
    so cleaning a category whose location was a junction deleted the real
    files inside the target (data loss). The broken CI masked this.
    """
    if os.name != "nt":
        pytest.skip("junctions are Windows-only")
    target = tmp_path / "target"
    target.mkdir()
    important = target / "important.txt"
    important.write_text("do not delete", encoding="utf-8")
    link = tmp_path / "link"
    if not _make_junction(link, target):
        pytest.skip("could not create a junction")

    category = CleanCategory("links", "Links", "", [str(link)])
    targets = [path for _rule, path in category._iter_targets()]
    assert targets == [str(link)], \
        "the junction must not expose its target's contents as targets"

    removed, errors, _freed = category.clean()

    assert removed == 1
    assert errors == 0
    assert important.exists(), "the junction target was deleted"
    assert not link.exists(), "the junction link itself must be removed"


def test_symlink_is_removed_without_following_target(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    important = target / "important.txt"
    important.write_text("do not delete", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are unavailable")

    category = CleanCategory("links", "Links", "", [str(link)])
    removed, errors, _freed = category.clean()

    assert removed == 1
    assert errors == 0
    assert important.exists()


def test_readonly_file_is_removed(tmp_path):
    path = tmp_path / "readonly.txt"
    path.write_text("data", encoding="utf-8")
    os.chmod(path, stat.S_IREAD)

    category = CleanCategory("readonly", "Readonly", "", [str(path)])
    removed, errors, _freed = category.clean()

    assert removed == 1
    assert errors == 0
    assert not path.exists()


def test_file_disappearing_after_preview_is_skipped(tmp_path):
    path = tmp_path / "vanishing.txt"
    path.write_text("data", encoding="utf-8")
    category = CleanCategory("vanishing", "Vanishing", "", [str(path)])
    category.list_files()
    path.unlink()

    removed, errors, _freed = category.clean()

    assert removed == 1
    assert errors == 0


def test_overlapping_categories_do_not_report_double_delete(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("data", encoding="utf-8")
    first = CleanCategory("first", "First", "", [str(path)])
    second = CleanCategory("second", "Second", "", [str(path)])

    first.clean()
    removed, errors, _freed = second.clean()

    assert removed == 0
    assert errors == 0
    assert not path.exists()
