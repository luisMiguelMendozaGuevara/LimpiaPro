"""Application services kept independent from the UI framework.

This package contains the core business logic services that are decoupled
from any specific UI framework. The PySide6 interface drives them through
the controller.

Exported Services:
    CacheService: Atomic JSON cache storage for scan results.
    CleanupService: Synchronous orchestration of scans, previews, and cleans.
"""

from .cache_service import CacheService
from .cleanup_service import CleanupService

__all__ = ["CacheService", "CleanupService"]
