"""Tests for UI-independent services."""

from limpiapro.services import CacheService, CleanupService, UiDispatcher


class FakeCategory:
    def __init__(self):
        self.size = 3
        self.scanned = False
        self.cleaned = False

    def scan(self, **_kwargs):
        self.scanned = True

    def list_files(self, limit):
        return ["a.txt"][:limit], 1

    def clean(self, **_kwargs):
        self.cleaned = True
        return 1, 0, 3


def test_cache_service_round_trips_versioned_data(tmp_path):
    service = CacheService(tmp_path / "cache.json", 1, "2.2")
    data = {"temp": {"size": 10, "files": 2}}
    service.save(data, "test-platform")

    assert service.load() == data


def test_cache_service_rejects_other_version(tmp_path):
    service = CacheService(tmp_path / "cache.json", 1, "2.2")
    service.save({"temp": {"size": 10, "files": 2}}, "test")
    other = CacheService(tmp_path / "cache.json", 1, "9.9")

    assert other.load() == {}


def test_cleanup_service_orchestrates_without_tkinter():
    category = FakeCategory()
    service = CleanupService()

    service.analyze([category])
    preview = service.preview([category])
    result = service.clean([category])

    assert category.scanned
    assert preview == [(category, ["a.txt"], 1)]
    assert category.cleaned
    assert result == (1, 0, 3)


def test_ui_dispatcher_posts_to_thread_safe_queue(monkeypatch):
    calls = []

    def callback():
        pass

    monkeypatch.setattr("limpiapro.services.ui_dispatcher.post_ui", calls.append)
    assert UiDispatcher().post(callback) is None
    assert calls == [callback]
