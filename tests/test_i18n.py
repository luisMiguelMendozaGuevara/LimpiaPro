"""Tests for the i18n module: language detection and the t() contract."""

import pytest

from limpiapro import i18n


@pytest.fixture(autouse=True)
def _restore_lang():
    """Keep the module-level LANG untouched between tests."""
    original = i18n.LANG
    yield
    i18n.LANG = original


def test_key_parity_between_languages():
    """Every key must exist in both language tables (and vice versa)."""
    es_keys = set(i18n._STRINGS["es"])
    en_keys = set(i18n._STRINGS["en"])
    assert es_keys == en_keys


def test_all_values_are_ascii():
    """Project convention: no accents/nn (Latin-1 range) in translation
    values, keeping them immune to code-page issues. Decorative emoji in
    the sidebar keys are allowed (Python source is UTF-8, tkinter renders
    them natively)."""
    for lang, table in i18n._STRINGS.items():
        for key, value in table.items():
            offenders = [ch for ch in value if 0x80 <= ord(ch) < 0x100]
            assert not offenders, f"{lang}/{key} has accents: {offenders}"


def test_t_interpolates_placeholders():
    i18n.LANG = "es"
    assert i18n.t("clean.n_files", n=3) == "3 archivos"
    i18n.LANG = "en"
    assert i18n.t("clean.n_files", n=3) == "3 files"


def test_t_without_format_args_returns_plain():
    i18n.LANG = "es"
    assert i18n.t("status.ready") == "Listo"


def test_t_unknown_key_returns_the_key_and_logs(monkeypatch):
    logged = []
    monkeypatch.setattr(i18n, "_errlog", lambda msg: logged.append(msg))
    assert i18n.t("no.such.key") == "no.such.key"
    assert any("no.such.key" in msg for msg in logged)


def test_t_falls_back_to_spanish_when_key_missing_in_lang(monkeypatch):
    i18n.LANG = "en"
    monkeypatch.setitem(i18n._STRINGS["en"], "test.only.es", None)
    i18n._STRINGS["es"]["test.only.es"] = "solo espanol"
    try:
        assert i18n.t("test.only.es") == "solo espanol"
    finally:
        del i18n._STRINGS["es"]["test.only.es"]
        del i18n._STRINGS["en"]["test.only.es"]


def test_detect_language_env_override(monkeypatch):
    monkeypatch.setenv("LIMPIAPRO_LANG", "en")
    assert i18n.detect_language() == "en"
    monkeypatch.setenv("LIMPIAPRO_LANG", "ES")
    assert i18n.detect_language() == "es"
    monkeypatch.setenv("LIMPIAPRO_LANG", "fr")
    # Unknown overrides fall through to the Windows detection.
    assert i18n.detect_language() in ("es", "en")


def test_detect_language_spanish_langid(monkeypatch):
    class _Kernel32:
        def GetUserDefaultUILanguage(self):
            return 0x0C0A  # Spanish (Spain)

    monkeypatch.setattr(i18n.ctypes.windll, "kernel32", _Kernel32())
    assert i18n.detect_language() == "es"


def test_detect_language_other_langid_maps_to_english(monkeypatch):
    class _Kernel32:
        def GetUserDefaultUILanguage(self):
            return 0x0409  # English (US)

    monkeypatch.setattr(i18n.ctypes.windll, "kernel32", _Kernel32())
    assert i18n.detect_language() == "en"


def test_detect_language_api_failure_falls_back_to_locale(monkeypatch):
    class _Broken:
        def GetUserDefaultUILanguage(self):
            raise OSError("no windows")

    monkeypatch.setattr(i18n.ctypes.windll, "kernel32", _Broken())
    monkeypatch.delenv("LIMPIAPRO_LANG", raising=False)
    monkeypatch.setattr(i18n._locale, "getdefaultlocale",
                        lambda: ("es_ES", "cp1252"))
    assert i18n.detect_language() == "es"
    monkeypatch.setattr(i18n._locale, "getdefaultlocale",
                        lambda: ("fr_FR", "cp1252"))
    assert i18n.detect_language() == "en"
