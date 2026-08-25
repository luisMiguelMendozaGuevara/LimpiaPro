"""Application services kept independent from the Tkinter UI.

This package contains the core business logic services that are decoupled
from any specific UI framework. This allows the same scanning, caching,
and cleanup logic to be used by both the legacy Tkinter interface and
the modern PySide6 interface.

Exported Services:
    CacheService: Atomic JSON cache storage for scan results.
    CleanupService: Synchronous orchestration of scans, previews, and cleans.
    UiDispatcher: Thread-safe bridge for posting callbacks to the UI thread.
"""

from .cache_service import CacheService
from .cleanup_service import CleanupService
from .ui_dispatcher import UiDispatcher

__all__ = ["CacheService", "CleanupService", "UiDispatcher"]
