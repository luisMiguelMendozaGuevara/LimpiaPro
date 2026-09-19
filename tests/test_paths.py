"""Per-user storage path tests."""

from limpiapro.paths import get_cache_file, get_logs_dir, get_user_data_dir


def test_user_data_paths_are_scoped_to_localappdata(monkeypatch, tmp_path):
    # conftest isolates every test under LIMPIAPRO_DATA_DIR; this test is
    # about the LOCALAPPDATA derivation, so the override is removed first.
    monkeypatch.delenv("LIMPIAPRO_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    user_dir = get_user_data_dir()

    assert user_dir == str(tmp_path / "Local" / "LimpiaPro")
    assert get_logs_dir() == str(tmp_path / "Local" / "LimpiaPro" / "logs")
    assert get_cache_file() == str(tmp_path / "Local" / "LimpiaPro" / "limpiador_cache.json")


def test_data_dir_override_wins(monkeypatch, tmp_path):
    """LIMPIAPRO_DATA_DIR (test isolation / portable) takes precedence."""
    monkeypatch.setenv("LIMPIAPRO_DATA_DIR", str(tmp_path / "iso"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    assert get_user_data_dir() == str(tmp_path / "iso")
    assert get_logs_dir() == str(tmp_path / "iso" / "logs")
    assert get_cache_file() == str(tmp_path / "iso" / "limpiador_cache.json")
