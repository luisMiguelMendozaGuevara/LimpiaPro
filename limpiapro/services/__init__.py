"""Application services kept independent from the UI framework.

This package contains the core business logic services that are decoupled
from any specific UI framework. The PySide6 interface drives them through
the controller.

Exported Services:
    CacheService: Atomic JSON cache storage for scan results.
"""

from .cache_service import CacheService

__all__ = ["CacheService"]
