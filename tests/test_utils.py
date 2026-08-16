"""Tests de utilidades puras."""

import os

from limpiapro.utils import (_delete_path, _fast_folder_stats, _folder_size,
                             _parallel_map, _safe_size, format_size, glob_like,
                             iter_file_sizes)

_PATH = "C:\\x"


def _write(base, *relpaths, content=b"datos"):
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


def test_glob_like_sin_comodines(tmp_path):
    assert glob_like(str(tmp_path)) == [str(tmp_path)]


def test_glob_like_con_comodines(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"")
    (tmp_path / "b.txt").write_bytes(b"")
    resultado = glob_like(os.path.join(str(tmp_path), "*.txt"))
    assert sorted(os.path.basename(p) for p in resultado) == ["a.txt", "b.txt"]


def test_iter_file_sizes_recorre_subcarpetas(tmp_path):
    _write(tmp_path, "a.log", "sub/b.dat", "sub/anidado/c.tmp", content=b"12345")
    pares = {(os.path.relpath(p, tmp_path).replace(os.sep, "/"), t)
             for p, t in iter_file_sizes(str(tmp_path))}
    assert pares == {("a.log", 5), ("sub/b.dat", 5),
                     ("sub/anidado/c.tmp", 5)}


def test_iter_file_sizes_carpeta_inexistente_no_revienta(tmp_path):
    assert list(iter_file_sizes(str(tmp_path / "no-existe"))) == []


def test_fast_folder_stats_cuenta_y_callback(tmp_path):
    _write(tmp_path, "a", "b", "sub/c")
    total, n = _fast_folder_stats(str(tmp_path))
    assert n == 3
    assert total == 15
    vistos = []
    _fast_folder_stats(str(tmp_path), lambda c: vistos.append(c))
    assert vistos == []  # menos de PROGRESS_STATS (500) archivos
    for i in range(510):
        (tmp_path / f"f{i:04d}").write_bytes(b"x")
    total, n = _fast_folder_stats(str(tmp_path), lambda c: vistos.append(c))
    assert n == 513
    assert vistos  # al menos una notificacion de progreso
    assert vistos[-1] == 500


def test_folder_size_suma(tmp_path):
    _write(tmp_path, "a", "b", "sub/c")
    assert _folder_size(str(tmp_path)) == 15


def test_safe_size_archivo_carpeta_e_inexistente(tmp_path):
    p = tmp_path / "archivo.bin"
    p.write_bytes(b"0123456789")
    assert _safe_size(str(p)) == 10
    sub = tmp_path / "carpeta"
    _write(sub, "x")
    assert _safe_size(str(sub)) == 5
    assert _safe_size(str(tmp_path / "no-existe")) == 0


def test_delete_path_archivo_carpeta_y_ya_eliminado(tmp_path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"x")
    assert _delete_path(str(f)) is True
    assert f.exists() is False
    d = tmp_path / "carpeta"
    _write(d, "vacio.txt")
    assert _delete_path(str(d)) is True
    assert d.exists() is False
    assert _delete_path(str(f)) is False  # ya no existe


def test_parallel_map_orden_y_errores(tmp_path):
    def duplica(x):
        return x * 2
    out = _parallel_map(duplica, [1, 2, 3], workers=2)
    assert out == [2, 4, 6]

    def falla(x):
        if x == 2:
            raise ValueError("boom")
        return x
    out = _parallel_map(falla, [1, 2, 3], workers=2)
    assert out == [1, None, 3]


def test_parallel_map_vacio():
    assert _parallel_map(lambda x: x, []) == []
