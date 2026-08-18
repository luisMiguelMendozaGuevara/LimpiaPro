"""Per-user storage path tests."""

from limpiapro.paths import get_cache_file, get_logs_dir, get_user_data_dir


def test_user_data_paths_are_scoped_to_localappdata(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))

    user_dir = get_user_data_dir()

    assert user_dir == str(tmp_path / "Local" / "LimpiaPro")
    assert get_logs_dir() == str(tmp_path / "Local" / "LimpiaPro" / "logs")
    assert get_cache_file() == str(tmp_path / "Local" / "LimpiaPro" / "limpiador_cache.json")
