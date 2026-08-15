"""Tests de CleanCategory sobre carpetas temporales."""

import os


def _make_cat(tmp_path):
    from limpiapro.categories import CleanCategory
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "cache" / "b.bin").write_bytes(b"y" * 50)
    (tmp_path / "suelto.txt").write_bytes(b"z" * 10)
    return CleanCategory("t", "Test", "", [str(tmp_path / "cache"),
                                           str(tmp_path / "suelto.txt")])


def test_scan_cuenta_tamano_y_archivos(tmp_path):
    cat = _make_cat(tmp_path)
    cat.scan()
    # cache/ tiene 2 archivos (a.bin=100 + b.bin=50), suelto.txt=10 => 3 ficheros
    assert cat.files == 3
    assert cat.size == 160


def test_list_files_sin_reglas_devuelve_primer_nivel(tmp_path):
    cat = _make_cat(tmp_path)
    files, scanned = cat.list_files()
    nombres = sorted(os.path.basename(f) for f in files)
    # la carpeta se borra entera al limpiar: la vista previa muestra el
    # nivel superior, no cada archivo interno
    assert nombres == ["a.bin", "b.bin", "suelto.txt"]
    assert scanned == 3


def test_clean_elimina_contenido_de_ubicaciones(tmp_path):
    cat = _make_cat(tmp_path)
    removed, errors, freed = cat.clean()
    assert errors == 0
    assert removed == 3
    assert freed == 160
    assert not (tmp_path / "cache" / "a.bin").exists()
    assert not (tmp_path / "suelto.txt").exists()


def test_ubicacion_inexistente_se_ignora(tmp_path):
    from limpiapro.categories import CleanCategory
    cat = CleanCategory("t", "Test", "", [str(tmp_path / "no_existe")])
    cat.scan()
    assert cat.files == 0
    assert cat.size == 0
