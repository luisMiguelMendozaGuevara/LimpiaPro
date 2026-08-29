"""Versioned JSON cache storage for per-user scan results.

This module provides atomic persistence for category scan results. It is
UI-independent and can be swapped for any other storage backend that
implements the CacheStore protocol.

Design Principles:
1. Atomicity: Uses tmp + os.replace to prevent partial writes.
2. Versioning: Schema and app_version prevent loading stale data after upgrades.
3. Best-Effort: Never raises on load/save failures; always returns safe defaults.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any

# How long a cached scan is considered fresh enough to skip the startup
# auto-analysis. Full rescans stay one click away (the Analyze button),
# and preview/clean always re-walk the filesystem, so a fresh-but-stale
# size only affects the numbers shown right after launch.
DEFAULT_FRESH_SECONDS = 6 * 3600


class CacheService:
    """Load and atomically persist category scan results.

    This service decouples the scanning logic (which runs on background threads)
    from the storage mechanism. It ensures that a crash or power loss during
    the write operation never leaves the cache file in a corrupted state.

    Attributes:
        path (Path): Filesystem path to the JSON cache file.
        schema (int): Integer schema version for cache invalidation.
        app_version (str): Application version string for invalidation.
    """

    def __init__(self, path: str | os.PathLike[str], schema: int, app_version: str):
        """Initialize the CacheService.

        Args:
            path: The filesystem path where the cache will be stored.
            schema: The schema version. If the file on disk has a different
                    schema, it is treated as invalid and discarded.
            app_version: The application version. If the file on disk was
                         saved by a different version, it is discarded.
        """
        self.path = Path(path)
        self.schema = schema
        self.app_version = app_version

    def load(self) -> dict[str, Any]:
        """Load cached data from disk.

        Returns:
            dict: The cached data dictionary. Returns an empty dict if:
                  - The file does not exist.
                  - The file is malformed JSON.
                  - The schema or app_version do not match.
                  - The 'data' field is missing or not a dict.

        Note:
            This method never raises. All IO and parsing errors are caught
            and result in an empty dict.
        """
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            # File missing, permission denied, or malformed JSON.
            return {}

        if not isinstance(raw, dict):
            return {}

        # CRITICAL: Version gating. Prevents loading old cache formats
        # after an app upgrade or schema change.
        if raw.get("schema") != self.schema or raw.get("app_version") != self.app_version:
            return {}

        data = raw.get("data")
        return data if isinstance(data, dict) else {}

    def age_seconds(self, now: float | None = None) -> float | None:
        """Age of the cache in seconds, or None when unknown.

        Uses the cache file's mtime, which is the moment the last
        successful save swapped the file into place. Works for caches
        written by any schema/version (no payload parsing needed).

        Args:
            now: Reference timestamp (defaults to time.time()).

        Returns:
            float | None: Age in seconds; None when the file does not
                          exist or cannot be stat'ed.
        """
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return None
        reference = time.time() if now is None else now
        return max(reference - mtime, 0.0)

    def is_fresh(
        self, max_age_seconds: float = DEFAULT_FRESH_SECONDS, now: float | None = None
    ) -> bool:
        """True when a cache file exists and is younger than the limit.

        Used by the startup flow to decide between showing cached sizes
        (instant, incremental behavior) and running the full auto-
        analysis. Any error reading the file counts as not fresh.

        Strictly younger (age < limit), not <=: age_seconds() clamps to
        a floor of 0.0 (Windows can round a freshly written file's mtime
        into the future), so with a 0-second window a brand-new cache
        must count as NOT fresh, not as just-barely-fresh.

        Args:
            max_age_seconds: Freshness window (DEFAULT_FRESH_SECONDS).
            now: Reference timestamp (defaults to time.time()).

        Returns:
            bool: True when the cache can stand in for a fresh analysis.
        """
        age = self.age_seconds(now=now)
        return age is not None and age < max_age_seconds

    def save(self, data: dict[str, dict[str, int]], platform_name: str) -> None:
        """Persist data atomically to disk.

        The write is performed to a temporary file first, then atomically
        swapped into place using os.replace. This ensures that a crash
        during the write operation does not corrupt the existing cache file.

        Args:
            data: Dictionary mapping category keys to their {size, files} results.
            platform_name: Identifier for the current OS platform (e.g., "win32").

        Note:
            This method never raises. OS errors during write are silently
            ignored, and the temporary file is cleaned up if possible.
        """
        payload = {
            "schema": self.schema,
            "app_version": self.app_version,
            "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "platform": platform_name,
            "data": data,
        }
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            # ATOMIC SWAP: os.replace is atomic on POSIX and Windows (with caveats).
            # This prevents half-written cache files.
            os.replace(tmp, self.path)
        except OSError:
            # Best-effort cleanup of the temporary file.
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
