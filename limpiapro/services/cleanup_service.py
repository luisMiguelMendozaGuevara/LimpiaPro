"""UI-independent cleanup orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


class CleanupService:
    """Coordinate category scans, previews and cleanups without Tkinter."""

    def analyze(
        self, categories: Iterable[Any], should_cancel: Callable[[], bool] | None = None
    ) -> None:
        for category in categories:
            if should_cancel and should_cancel():
                return
            category.scan(should_cancel=should_cancel)

    def preview(
        self, categories: Iterable[Any], limit: int = 1000
    ) -> list[tuple[Any, list[str], int]]:
        result = []
        for category in categories:
            files, scanned = category.list_files(limit)
            result.append((category, files, scanned))
        return result

    def clean(
        self,
        categories: Iterable[Any],
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[Any, float], None] | None = None,
    ) -> tuple[int, int, int]:
        removed = errors = freed = 0
        for category in categories:
            if should_cancel and should_cancel():
                break
            result = category.clean(
                target_bytes=category.size,
                should_cancel=should_cancel,
                on_progress=(lambda fraction, c=category: on_progress(c, fraction))
                if on_progress
                else None,
            )
            r, e, f = result
            removed += r
            errors += e
            freed += f
        return removed, errors, freed
