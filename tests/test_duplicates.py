"""Tests for the duplicate file finder."""

import os

from limpiapro.duplicates import DuplicateScanner


def test_finds_group_of_duplicates(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"identical content" * 10)
    (tmp_path / "b.bin").write_bytes(b"identical content" * 10)
    (tmp_path / "c.bin").write_bytes(b"something else" * 10)

    scanner = DuplicateScanner(str(tmp_path), min_size_mb=0, workers=2)
    groups = scanner.scan()

    assert len(groups) == 1
    assert len(groups[0]) == 2
    names = sorted(os.path.basename(p) for p in groups[0])
    assert names == ["a.bin", "b.bin"]


def test_different_files_are_not_grouped(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"aaaa")
    (tmp_path / "b.bin").write_bytes(b"bbbb")

    scanner = DuplicateScanner(str(tmp_path), min_size_mb=0, workers=2)
    assert scanner.scan() == []


def test_min_size_filters(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "b.bin").write_bytes(b"x" * 100)

    scanner = DuplicateScanner(str(tmp_path), min_size_mb=1, workers=2)
    assert scanner.scan() == []


def test_cancel_stops_the_scan(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    scanner = DuplicateScanner(str(tmp_path), min_size_mb=0, workers=2)
    scanner.cancel = True
    assert scanner.scan() == []
