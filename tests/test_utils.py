"""Tests de utilidades puras."""

import os

from limpiapro.utils import format_size, glob_like


def test_format_size():
    assert format_size(0) == "0 B"
    assert format_size(512) == "512 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024 * 3) == "3.0 MB"
    assert format_size(-5) == "-"


def test_glob_like_sin_comodines(tmp_path):
    assert glob_like(str(tmp_path)) == [str(tmp_path)]


def test_glob_like_con_comodines(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"")
    (tmp_path / "b.txt").write_bytes(b"")
    resultado = glob_like(os.path.join(str(tmp_path), "*.txt"))
    assert sorted(os.path.basename(p) for p in resultado) == ["a.txt", "b.txt"]
