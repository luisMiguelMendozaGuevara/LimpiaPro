"""Tests del parser winapp2 (formato, deteccion, exclusiones)."""

import os

import pytest

from limpiapro import winapp2
from limpiapro.categories import CleanCategory
from limpiapro.winapp2 import ExcludeKey, parse_sections


def _write_files(base, names, content=b"datos"):
    for name in names:
        p = base / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)


# ------------------------------------------------------------------ parseo

def test_filekey_formato_estandar():
    text = "[App]\nFileKey1=%TEMP%\\x|*.log;*.tmp|RECURSE\n"
    (section,) = parse_sections(text)
    (rule,) = section["rules"]
    assert rule.root == r"%TEMP%\x"
    assert rule.recurse is True
    assert rule.patterns == ("*.log", "*.tmp")
    assert rule.remove_self is False


def test_filekey_sin_flag_no_recursa():
    text = "[App]\nFileKey1=C:\\dir|*.log\n"
    (rule,) = parse_sections(text)[0]["rules"]
    assert rule.recurse is False


def test_filekey_removeself_y_mascara_todo():
    text = "[App]\nFileKey1=C:\\dir|*.*|REMOVESELF\n"
    (rule,) = parse_sections(text)[0]["rules"]
    assert rule.remove_self is True
    assert rule.patterns == ("*",)  # *.* significa cualquier archivo


def test_filekey_ruta_con_asterisco_final_recursa():
    text = "[App]\nFileKey1=C:\\dir\\*|*.log\n"
    (rule,) = parse_sections(text)[0]["rules"]
    assert rule.recurse is True
    assert rule.root == r"C:\dir"


def test_detect_indexadas_y_compatibilidad():
    text = ("[App]\n"
            "Detect=HKCU\\Software\\A\n"
            "Detect1=HKCU\\Software\\B\n"
            "DetectFile1=%TEMP%\\existe\n")
    (section,) = parse_sections(text)
    assert section["detects"] == [
        r"HKCU\Software\A", r"HKCU\Software\B", r"%TEMP%\existe"]


def test_seccion_solo_specialdetect_se_descarta():
    text = "[App]\nSpecialDetect=DET_CHROME\nFileKey1=C:\\x|*.log\n"
    (section,) = parse_sections(text)
    assert winapp2.active_sections([section]) == []


def test_detects_se_combinan_con_and(monkeypatch):
    text = ("[App]\n"
            "Detect1=HKCU\\Software\\Si\n"
            "Detect2=HKCU\\Software\\No\n"
            "FileKey1=C:\\x|*.log\n")
    (section,) = parse_sections(text)
    valores = {r"HKCU\Software\Si": True, r"HKCU\Software\No": False}
    monkeypatch.setattr(winapp2, "detect_true",
                        lambda cond: valores[cond])
    assert winapp2.active_sections([section]) == []
    valores[r"HKCU\Software\No"] = True
    assert winapp2.active_sections([section]) == [section]


def test_detect_true_clave_existente():
    assert winapp2.detect_true(r"HKLM\Software\Microsoft") is True
    assert winapp2.detect_true(r"HKLM\Software\clave_que_no_existe_xyz") is False


# ------------------------------------------------------------------ exclusiones

def test_excludekey_basica_y_recursiva(tmp_path):
    ex = ExcludeKey.parse(str(tmp_path) + "|*.ini;*.cfg")
    assert ex.recursive is False
    assert ex.patterns == ("*.ini", "*.cfg")
    ex_rec = ExcludeKey.parse(str(tmp_path / "dir" / "*") + "|*.ini")
    assert ex_rec.recursive is True


def test_excludekey_reg_se_ignora():
    assert ExcludeKey.parse(r"REG|HKCU\Software\X|valor") is None


def test_exclusion_protege_archivos_en_scan_lista_y_limpieza(tmp_path):
    _write_files(tmp_path, ["a.log", "a.keep", "b.cfg"])
    text = (f"[App]\n"
            f"FileKey1={tmp_path}|*.*\n"
            f"ExcludeKey1={tmp_path}|*.keep;*.cfg\n")
    (section,) = parse_sections(text)
    cat = CleanCategory("t", "Test", "", [])
    cat.rules = section["rules"]

    files, scanned = cat.list_files()
    nombres = sorted(os.path.basename(f) for f in files)
    assert nombres == ["a.log"]
    assert scanned == 1

    cat.scan()
    assert cat.files == 1

    removed, errors, _freed = cat.clean()
    assert removed == 1 and errors == 0
    assert (tmp_path / "a.log").exists() is False
    assert (tmp_path / "a.keep").exists() is True
    assert (tmp_path / "b.cfg").exists() is True


def test_exclusion_recursiva(tmp_path):
    _write_files(tmp_path / "sub" / "x", ["a.txt", "a.dat"])
    text = (f"[App]\n"
            f"FileKey1={tmp_path}|*.*|RECURSE\n"
            f"ExcludeKey1={tmp_path}\\*|*.dat\n")
    (section,) = parse_sections(text)
    cat = CleanCategory("t", "Test", "", [])
    cat.rules = section["rules"]

    cat.scan()
    assert cat.files == 1  # solo a.txt; a.dat queda protegido


def test_removeself_borra_carpeta_vacia(tmp_path):
    _write_files(tmp_path, ["a.log"])
    text = f"[App]\nFileKey1={tmp_path}|*.*|REMOVESELF\n"
    (section,) = parse_sections(text)
    cat = CleanCategory("t", "Test", "", [])
    cat.rules = section["rules"]

    removed, _errors, _freed = cat.clean()
    assert removed == 1
    assert tmp_path.exists() is False  # carpeta eliminada al quedar vacia


def test_removeself_no_borra_carpeta_con_contenido_protegido(tmp_path):
    _write_files(tmp_path, ["a.log", "a.keep"])
    text = (f"[App]\n"
            f"FileKey1={tmp_path}|*.*|REMOVESELF\n"
            f"ExcludeKey1={tmp_path}|*.keep\n")
    (section,) = parse_sections(text)
    cat = CleanCategory("t", "Test", "", [])
    cat.rules = section["rules"]

    cat.clean()
    assert tmp_path.exists() is True  # a.keep la mantiene viva
    assert (tmp_path / "a.keep").exists()


# ------------------------------------------------------------------ ini real

def test_ini_real_smoke():
    path = winapp2.default_winapp_file()
    if not os.path.exists(path):
        pytest.skip("winapp2.ini no esta presente")
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        sections = parse_sections(f.read())
    assert len(sections) > 3000
    for s in sections[:50]:
        for rule in s["rules"]:
            assert rule.root
            assert rule.patterns
