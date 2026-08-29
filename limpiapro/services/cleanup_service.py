"""UI-independent cleanup orchestration.

This module provides a synchronous API for scanning, previewing, and cleaning
categories. It is designed to be used by background threads or CLI tools,
without any dependency on Tkinter or Qt.

The controller (controller.py) wraps this service in QThread workers to
provide the asynchronous UI experience.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any


class CleanupService:
    """Coordinate category scans, previews and cleanups without Tkinter.

    This service is stateless and thread-safe. It simply iterates over the
    provided categories and invokes their respective methods, passing along
    the cancellation and progress callbacks.

    Design Principle:
        The service does not own the categories. It receives them as an
        iterable, making it easy to test and reuse across different UIs.
    """

    def analyze(
        self, categories: Iterable[Any], should_cancel: Callable[[], bool] | None = None
    ) -> None:
        """Scan all categories to compute their sizes and file counts.

        Args:
            categories: An iterable of CleanCategory instances.
            should_cancel: A zero-argument callable that returns True if
                           the operation should be aborted. Checked between
                           each category scan.
        """
        for category in categories:
            # Cooperative cancellation: check before starting each category.
            if should_cancel and should_cancel():
                return
            category.scan(should_cancel=should_cancel)

    def preview(
        self, categories: Iterable[Any], limit: int = 1000
    ) -> list[tuple[Any, list[str], int]]:
        """Collect preview file lists for the given categories.

        Args:
            categories: An iterable of CleanCategory instances.
            limit: Maximum number of files to collect per category.

        Returns:
            list: A list of tuples: (category, [file_paths], scanned_count).
                  The category's internal snapshot is updated as a side effect.
        """
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
        """Execute deletion for the given categories.

        Args:
            categories: An iterable of CleanCategory instances.
            should_cancel: A zero-argument callable that returns True if
                           the operation should be aborted. Checked between
                           each category clean.
            on_progress: A callback invoked with (category, fraction) to
                         report progress. Fraction is 0.0 to 1.0 for the
                         current category.

        Returns:
            tuple: (total_removed, total_errors, total_freed_bytes).
        """
        removed = errors = freed = 0
        for category in categories:
            if should_cancel and should_cancel():
                break

            # Build the progress callback with a closure to capture the
            # current category reference.
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
