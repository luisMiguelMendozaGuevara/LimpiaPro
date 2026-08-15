"""Tests del buscador de duplicados."""

import os

from limpiapro.duplicates import DuplicateScanner


def test_encuentra_grupo_de_duplicados(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"contenido identico" * 10)
    (tmp_path / "b.bin").write_bytes(b"contenido identico" * 10)
    (tmp_path / "c.bin").write_bytes(b"otra cosa" * 10)

    scanner = DuplicateScanner(str(tmp_path), min_size_mb=0, workers=2)
    groups = scanner.scan()

    assert len(groups) == 1
    assert len(groups[0]) == 2
    nombres = sorted(os.path.basename(p) for p in groups[0])
    assert nombres == ["a.bin", "b.bin"]


def test_archivos_distintos_no_agrupan(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"aaaa")
    (tmp_path / "b.bin").write_bytes(b"bbbb")

    scanner = DuplicateScanner(str(tmp_path), min_size_mb=0, workers=2)
    assert scanner.scan() == []


def test_min_size_filtra(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    (tmp_path / "b.bin").write_bytes(b"x" * 100)

    scanner = DuplicateScanner(str(tmp_path), min_size_mb=1, workers=2)
    assert scanner.scan() == []


def test_cancel_detiene_el_escaneo(tmp_path):
    (tmp_path / "a.bin").write_bytes(b"x" * 100)
    scanner = DuplicateScanner(str(tmp_path), min_size_mb=0, workers=2)
    scanner.cancel = True
    assert scanner.scan() == []
