"""Hostile filesystem cases for destructive cleanup operations."""

import os
import stat

import pytest

from limpiapro.categories import CleanCategory


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
