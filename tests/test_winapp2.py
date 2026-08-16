"""Tests for the winapp2 parser (format, detection, exclusions)."""

import os

import pytest

from limpiapro import winapp2
from limpiapro.categories import CleanCategory
from limpiapro.winapp2 import ExcludeKey, parse_sections


@pytest.fixture(autouse=True)
def _clear_detect_cache():
    winapp2._DETECT_CACHE.clear()
    yield
    winapp2._DETECT_CACHE.clear()


def _write_files(base, names, content=b"data"):
    for name in names:
        p = base / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)


# ------------------------------------------------------------------ parsing

def test_filekey_standard_format():
    text = "[App]\nFileKey1=%TEMP%\\x|*.log;*.tmp|RECURSE\n"
    (section,) = parse_sections(text)
    (rule,) = section.rules
    assert rule.root == r"%TEMP%\x"
    assert rule.recurse is True
    assert rule.patterns == ("*.log", "*.tmp")
    assert rule.remove_self is False


def test_filekey_without_flag_does_not_recurse():
    text = "[App]\nFileKey1=C:\\dir|*.log\n"
    (rule,) = parse_sections(text)[0].rules
    assert rule.recurse is False


def test_filekey_removeself_and_any_file_mask():
    text = "[App]\nFileKey1=C:\\dir|*.*|REMOVESELF\n"
    (rule,) = parse_sections(text)[0].rules
    assert rule.remove_self is True
    assert rule.patterns == ("*",)  # *.* means any file


def test_filekey_path_with_trailing_asterisk_recurses():
    text = "[App]\nFileKey1=C:\\dir\\*|*.log\n"
    (rule,) = parse_sections(text)[0].rules
    assert rule.recurse is True
    assert rule.root == r"C:\dir"


def test_detect_indexed_and_compat_forms():
    text = ("[App]\n"
            "Detect=HKCU\\Software\\A\n"
            "Detect1=HKCU\\Software\\B\n"
            "DetectFile1=%TEMP%\\exists\n")
    (section,) = parse_sections(text)
    assert section.detects == [
        r"HKCU\Software\A", r"HKCU\Software\B", r"%TEMP%\exists"]


def test_section_with_only_specialdetect_is_discarded():
    text = "[App]\nSpecialDetect=DET_CHROME\nFileKey1=C:\\x|*.log\n"
    (section,) = parse_sections(text)
    assert winapp2.active_sections([section]) == []


def test_detects_combine_with_and(monkeypatch):
    text = ("[App]\n"
            "Detect1=HKCU\\Software\\Yes\n"
            "Detect2=HKCU\\Software\\No\n"
            "FileKey1=C:\\x|*.log\n")
    (section,) = parse_sections(text)
    values = {r"HKCU\Software\Yes": True, r"HKCU\Software\No": False}
    monkeypatch.setattr(winapp2, "detect_true",
                        lambda cond: values[cond])
    assert winapp2.active_sections([section]) == []
    values[r"HKCU\Software\No"] = True
    assert winapp2.active_sections([section]) == [section]


def test_detect_true_existing_key():
    assert winapp2.detect_true(r"HKLM\Software\Microsoft") is True
    assert winapp2.detect_true(r"HKLM\Software\key_that_does_not_exist_xyz") is False


# ------------------------------------------------------------------ exclusions

def test_excludekey_basic_and_recursive(tmp_path):
    ex = ExcludeKey.parse(str(tmp_path) + "|*.ini;*.cfg")
    assert ex.recursive is False
    assert ex.patterns == ("*.ini", "*.cfg")
    ex_rec = ExcludeKey.parse(str(tmp_path / "dir" / "*") + "|*.ini")
    assert ex_rec.recursive is True


def test_excludekey_reg_is_ignored():
    assert ExcludeKey.parse(r"REG|HKCU\Software\X|value") is None


def test_exclusion_protects_files_in_scan_list_and_clean(tmp_path):
    _write_files(tmp_path, ["a.log", "a.keep", "b.cfg"])
    text = (f"[App]\n"
            f"FileKey1={tmp_path}|*.*\n"
            f"ExcludeKey1={tmp_path}|*.keep;*.cfg\n")
    (section,) = parse_sections(text)
    cat = CleanCategory("t", "Test", "", [])
    cat.rules = section.rules

    files, scanned = cat.list_files()
    names = sorted(os.path.basename(f) for f in files)
    assert names == ["a.log"]
    assert scanned == 1

    cat.scan()
    assert cat.files == 1

    removed, errors, _freed = cat.clean()
    assert removed == 1 and errors == 0
    assert (tmp_path / "a.log").exists() is False
    assert (tmp_path / "a.keep").exists() is True
    assert (tmp_path / "b.cfg").exists() is True


def test_recursive_exclusion(tmp_path):
    _write_files(tmp_path / "sub" / "x", ["a.txt", "a.dat"])
    text = (f"[App]\n"
            f"FileKey1={tmp_path}|*.*|RECURSE\n"
            f"ExcludeKey1={tmp_path}\\*|*.dat\n")
    (section,) = parse_sections(text)
    cat = CleanCategory("t", "Test", "", [])
    cat.rules = section.rules

    cat.scan()
    assert cat.files == 1  # only a.txt; a.dat stays protected


def test_removeself_deletes_empty_folder(tmp_path):
    _write_files(tmp_path, ["a.log"])
    text = f"[App]\nFileKey1={tmp_path}|*.*|REMOVESELF\n"
    (section,) = parse_sections(text)
    cat = CleanCategory("t", "Test", "", [])
    cat.rules = section.rules

    removed, _errors, _freed = cat.clean()
    assert removed == 1
    assert tmp_path.exists() is False  # folder removed once empty


def test_removeself_keeps_folder_with_protected_content(tmp_path):
    _write_files(tmp_path, ["a.log", "a.keep"])
    text = (f"[App]\n"
            f"FileKey1={tmp_path}|*.*|REMOVESELF\n"
            f"ExcludeKey1={tmp_path}|*.keep\n")
    (section,) = parse_sections(text)
    cat = CleanCategory("t", "Test", "", [])
    cat.rules = section.rules

    cat.clean()
    assert tmp_path.exists() is True  # a.keep keeps it alive
    assert (tmp_path / "a.keep").exists()


def test_masks_with_comma_and_dotstar():
    text = "[App]\nFileKey1=C:\\dir|*.log,*.tmp|RECURSE\n"
    (rule,) = parse_sections(text)[0].rules
    assert rule.patterns == ("*.log", "*.tmp")
    text2 = "[App]\nFileKey1=C:\\dir|*.*\n"
    (rule2,) = parse_sections(text2)[0].rules
    assert rule2.patterns == ("*",)  # *.* normalizes to *


def test_excludekey_exact_file_variant(tmp_path):
    _write_files(tmp_path, ["a.log", "b.log"])
    ex = ExcludeKey.parse(f"FILE|{tmp_path}\\a.log")
    assert ex.exact is not None
    assert ex.matches(os.path.normcase(str(tmp_path / "a.log"))) is True
    assert ex.matches(os.path.normcase(str(tmp_path / "b.log"))) is False


def test_section_without_rules_is_discarded():
    text = "[App]\nDetect=HKCU\\Software\\Yes\n"
    (section,) = parse_sections(text)
    assert winapp2.active_sections([section]) == []


def test_invalid_lines_are_ignored():
    text = ("garbage without equals\n"
            "[App]\n"
            "FileKey1=C:\\dir|*.log\n"
            "=nokey\n"
            "KeyWithoutValue=\n"
            "[good-section]\n"
            "FileKey1=C:\\dir2|*.tmp\n"
            "[  ]\n"
            "FileKey1=C:\\ignored|*.*\n")
    (a, b) = parse_sections(text)
    assert a.name == "App"
    assert a.rules[0].root == r"C:\dir"
    assert b.name == "good-section"
    assert b.rules[0].root == r"C:\dir2"


def test_detectfile_with_wildcards(tmp_path):
    _write_files(tmp_path, ["detection.log"])
    cond = f"DetectFile={tmp_path}\\det*"
    assert winapp2._detect_true(cond.replace("DetectFile=", "")) is True
    assert winapp2._detect_true(f"{tmp_path}\\nope*") is False


def test_detect_true_returns_false_on_error():
    assert winapp2._detect_true(None) is False
    assert winapp2._detect_true("") is False


class _FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_detect_true_memoizes_registry_queries(monkeypatch):
    """The same condition queried twice must touch the registry once."""
    import winreg
    calls = []

    def fake_open(*_a):
        calls.append(1)
        return _FakeKey()

    monkeypatch.setattr(winapp2.winreg, "OpenKey", fake_open)
    cond = r"HKLM\Software\MemoKey1"
    assert winapp2.detect_true(cond) is True
    assert winapp2.detect_true(cond) is True
    assert len(calls) == 1


def test_detect_true_distinct_conditions_do_not_share_cache(monkeypatch):
    import winreg

    def fake_open(*_a):
        raise OSError("does not exist")

    monkeypatch.setattr(winapp2.winreg, "OpenKey", fake_open)
    winapp2.detect_true(r"HKLM\Software\MemoKeyA")
    winapp2.detect_true(r"HKLM\Software\MemoKeyB")
    winapp2.detect_true(r"HKLM\Software\MemoKeyA")
    # The cache does its job (not directly checkable without
    # introspection); what matters is that distinct keys never share a
    # cached result.
    assert winapp2._DETECT_CACHE[r"HKLM\Software\MemoKeyA"] is False
    assert len(winapp2._DETECT_CACHE) == 2


def test_parse_winapp_rules_returns_active_sections(tmp_path, monkeypatch):
    text = ("[A]\nDetect=HKCU\\Software\\Yes\nFileKey1=C:\\x|*.log\n"
            "[B]\nDetect=HKCU\\Software\\No\nFileKey1=C:\\y|*.tmp\n")
    ini = tmp_path / "winapp2.ini"
    ini.write_text(text, encoding="utf-8")
    monkeypatch.setattr(winapp2, "detect_true",
                        lambda cond: cond == r"HKCU\Software\Yes")
    sections = winapp2.parse_winapp_rules(str(ini))
    assert [s.name for s in sections] == ["A"]


# ------------------------------------------------------------------ real ini

def test_real_ini_smoke():
    path = winapp2.default_winapp_file()
    if not os.path.exists(path):
        pytest.skip("winapp2.ini not present")
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        sections = parse_sections(f.read())
    assert len(sections) > 3000
    for s in sections[:50]:
        for rule in s.rules:
            assert rule.root
            assert rule.patterns
