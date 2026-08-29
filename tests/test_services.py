"""Tests for UI-independent services."""

import os

from limpiapro.services import CacheService, CleanupService
from limpiapro.services.cache_service import DEFAULT_FRESH_SECONDS


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


# ------------------------------------- B1 cache freshness (startup skip)


def test_fresh_cache_is_detected_as_fresh(tmp_path):
    service = CacheService(tmp_path / "cache.json", 1, "2.5")
    service.save({"temp": {"size": 10, "files": 2}}, "test")

    assert service.age_seconds() is not None
    assert service.age_seconds() < 60
    assert service.is_fresh()


def test_backdated_cache_is_not_fresh(tmp_path):
    import time as _t

    service = CacheService(tmp_path / "cache.json", 1, "2.5")
    service.save({"temp": {"size": 10, "files": 2}}, "test")
    # Backdate the file 2 * freshness window (mtime = save time).
    old = _t.time() - 2 * DEFAULT_FRESH_SECONDS
    os.utime(service.path, (old, old))

    assert not service.is_fresh()
    assert not service.is_fresh(DEFAULT_FRESH_SECONDS)


def test_missing_cache_is_never_fresh(tmp_path):
    service = CacheService(tmp_path / "absent.json", 1, "2.5")

    assert service.age_seconds() is None
    assert not service.is_fresh()


def test_is_fresh_respects_custom_window(tmp_path):
    service = CacheService(tmp_path / "cache.json", 1, "2.5")
    service.save({"temp": {"size": 10, "files": 2}}, "test")
    # A 1-second-old cache is "fresh" for a 1h window, not for a 0s one.
    assert service.is_fresh(3600)
    assert not service.is_fresh(0)


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
