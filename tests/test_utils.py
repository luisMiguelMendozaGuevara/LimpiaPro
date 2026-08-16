"""Tests for pure utilities."""

import os

from limpiapro.utils import (_delete_path, _fast_folder_stats, _folder_size,
                             _parallel_map, _safe_size, format_size, glob_like,
                             iter_file_sizes)


def _write(base, *relpaths, content=b"12345"):
    for rel in relpaths:
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)


def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(512) == "512 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024 * 3) == "3.0 MB"
    assert format_size(-5) == "-"


def test_glob_like_without_wildcards(tmp_path):
    assert glob_like(str(tmp_path)) == [str(tmp_path)]


def test_glob_like_with_wildcards(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"")
    (tmp_path / "b.txt").write_bytes(b"")
    result = glob_like(os.path.join(str(tmp_path), "*.txt"))
    assert sorted(os.path.basename(p) for p in result) == ["a.txt", "b.txt"]


def test_iter_file_sizes_walks_subfolders(tmp_path):
    _write(tmp_path, "a.log", "sub/b.dat", "sub/nested/c.tmp", content=b"12345")
    pairs = {(os.path.relpath(p, tmp_path).replace(os.sep, "/"), size)
             for p, size in iter_file_sizes(str(tmp_path))}
    assert pairs == {("a.log", 5), ("sub/b.dat", 5),
                     ("sub/nested/c.tmp", 5)}


def test_iter_file_sizes_missing_folder_does_not_crash(tmp_path):
    assert list(iter_file_sizes(str(tmp_path / "missing"))) == []


def test_fast_folder_stats_counts_and_calls_back(tmp_path):
    _write(tmp_path, "a", "b", "sub/c")
    total, n = _fast_folder_stats(str(tmp_path))
    assert n == 3
    assert total == 15
    seen = []
    _fast_folder_stats(str(tmp_path), lambda count: seen.append(count))
    assert seen == []  # fewer than PROGRESS_STATS (500) files
    for i in range(510):
        (tmp_path / f"f{i:04d}").write_bytes(b"x")
    total, n = _fast_folder_stats(str(tmp_path), lambda count: seen.append(count))
    assert n == 513
    assert seen  # at least one progress notification
    assert seen[-1] == 500


def test_folder_size_sums(tmp_path):
    _write(tmp_path, "a", "b", "sub/c")
    assert _folder_size(str(tmp_path)) == 15


def test_safe_size_file_folder_and_missing(tmp_path):
    p = tmp_path / "file.bin"
    p.write_bytes(b"0123456789")
    assert _safe_size(str(p)) == 10
    sub = tmp_path / "folder"
    _write(sub, "x")
    assert _safe_size(str(sub)) == 5
    assert _safe_size(str(tmp_path / "missing")) == 0


def test_delete_path_file_folder_and_already_gone(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    assert _delete_path(str(f)) is True
    assert f.exists() is False
    d = tmp_path / "folder"
    _write(d, "empty.txt")
    assert _delete_path(str(d)) is True
    assert d.exists() is False
    assert _delete_path(str(f)) is False  # already gone


def test_parallel_map_order_and_errors(tmp_path):
    def double(x):
        return x * 2
    out = _parallel_map(double, [1, 2, 3], workers=2)
    assert out == [2, 4, 6]

    def failing(x):
        if x == 2:
            raise ValueError("boom")
        return x
    out = _parallel_map(failing, [1, 2, 3], workers=2)
    assert out == [1, None, 3]


def test_parallel_map_empty():
    assert _parallel_map(lambda x: x, []) == []
