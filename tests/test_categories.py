"""Tests for CleanCategory over temporary folders."""

import os


def _make_cat(tmp_path):
    from limpiapro.categories import CleanCategory
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "cache" / "b.bin").write_bytes(b"y" * 50)
    (tmp_path / "loose.txt").write_bytes(b"z" * 10)
    return CleanCategory("t", "Test", "", [str(tmp_path / "cache"),
                                           str(tmp_path / "loose.txt")])


def test_scan_counts_size_and_files(tmp_path):
    cat = _make_cat(tmp_path)
    cat.scan()
    # cache/ has 2 files (a.bin=100 + b.bin=50), loose.txt=10 => 3 files
    assert cat.files == 3
    assert cat.size == 160


def test_list_files_without_rules_returns_top_level(tmp_path):
    cat = _make_cat(tmp_path)
    files, scanned = cat.list_files()
    names = sorted(os.path.basename(f) for f in files)
    # folders are deleted whole when cleaning: the preview shows the top
    # level, not every internal file
    assert names == ["a.bin", "b.bin", "loose.txt"]
    assert scanned == 3


def test_clean_deletes_location_contents(tmp_path):
    cat = _make_cat(tmp_path)
    removed, errors, freed = cat.clean()
    assert errors == 0
    assert removed == 3
    assert freed == 160
    assert not (tmp_path / "cache" / "a.bin").exists()
    assert not (tmp_path / "loose.txt").exists()


def test_missing_location_is_ignored(tmp_path):
    from limpiapro.categories import CleanCategory
    cat = CleanCategory("t", "Test", "", [str(tmp_path / "does_not_exist")])
    cat.scan()
    assert cat.files == 0
    assert cat.size == 0
