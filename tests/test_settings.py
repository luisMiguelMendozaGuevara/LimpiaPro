"""Settings persistence (limpiapro.settings)."""

import json

from limpiapro.settings import Settings


def test_settings_roundtrip(tmp_path):
    path = str(tmp_path / "settings.json")
    s = Settings(theme="light", language="es", auto_analyze=False,
                 confirm_before_clean=False)
    s.save(path)
    loaded = Settings.load(path)
    assert loaded.theme == "light"
    assert loaded.language == "es"
    assert loaded.auto_analyze is False
    assert loaded.confirm_before_clean is False


def test_settings_missing_file_returns_defaults(tmp_path):
    loaded = Settings.load(str(tmp_path / "missing.json"))
    assert loaded.theme == "dark"
    assert loaded.auto_analyze is True


def test_settings_ignores_unknown_and_bad_values(tmp_path):
    path = str(tmp_path / "settings.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"theme": "neon", "language": "xx", "bogus": 1,
                   "auto_analyze": "yes"}, f)
    loaded = Settings.load(path).validate()
    assert loaded.theme == "dark"      # coerced back to a valid value
    assert loaded.language == "auto"
    assert loaded.auto_analyze is True  # non-bool ignored


def test_settings_save_is_atomic(tmp_path):
    path = str(tmp_path / "settings.json")
    Settings(theme="dark").save(path)
    # no leftover temp file after a successful save
    assert not (tmp_path / "settings.json.tmp").exists()
    with open(path, encoding="utf-8") as fh:
        assert json.loads(fh.read())["theme"] == "dark"
