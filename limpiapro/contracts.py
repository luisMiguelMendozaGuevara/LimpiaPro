"""Structural contracts shared by pages and application services.

This module defines Protocol classes (PEP 544 - Structural Subtyping)
that serve as interfaces between the UI pages and the application core.

Design Principles:
1. Decoupling: Pages depend on Protocols, not concrete classes. This
   allows the same page to work with different backends (e.g., legacy
   Tkinter app vs modern PySide6 controller).
2. Minimal Surface: Each Protocol exposes only the methods/attributes
   that the consumer actually needs, preventing tight coupling.
3. Type Safety: Enables static type checkers (mypy, pyright) to verify
   that the UI and core are compatible without runtime inheritance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class CacheStore(Protocol):
    """Protocol for a cache backend that stores category scan results.

    Implementations: CacheService (services/cache_service.py)
    """
    def load(self) -> dict[str, Any]:
        """Load cached data from storage."""
        ...

    def save(self, data: dict[str, dict[str, int]], platform_name: str) -> None:
        """Persist data to storage.

        Args:
            data: Dictionary mapping category keys to {size, files}.
            platform_name: Identifier for the current OS platform.
        """
        ...


class CleanCategoryProtocol(Protocol):
    """Protocol for a cleaning category.

    This defines the interface that all category objects must implement
    to be compatible with the controller and pages.

    Implementations: CleanCategory (categories.py)
    """
    # Attributes
    key: str
    label: str
    description: str
    icon: str
    needs_admin: bool
    size: int
    files: int
    recycle_bin: bool

    def scan(
        self,
        on_progress: Callable[[int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> int:
        """Scan the category to compute size and file count.

        Args:
            on_progress: Callback invoked with the number of files scanned so far.
            should_cancel: Callback that returns True if the scan should abort.

        Returns:
            int: The number of files scanned.
        """
        ...

    def list_files(self, limit: int = 1000) -> tuple[list[str], int]:
        """Collect a list of files to be cleaned (preview).

        Args:
            limit: Maximum number of files to collect.

        Returns:
            tuple: (list_of_file_paths, total_scanned_count).
        """
        ...

    def clean(
        self,
        target_bytes: int = 0,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[int, int, int]:
        """Execute the deletion operation.

        Args:
            target_bytes: Expected total bytes to free (for progress calculation).
            on_progress: Callback invoked with progress fraction (0.0 to 1.0).
            should_cancel: Callback that returns True if the clean should abort.

        Returns:
            tuple: (removed_count, error_count, freed_bytes).
        """
        ...

    def error_summary(self) -> dict[str, int]:
        """Return a summary of deletion errors by category.

        Returns:
            dict: Mapping of error type (e.g., "access_denied") to count.
        """
        ...


class UiDispatcherProtocol(Protocol):
    """Protocol for a UI thread dispatcher.

    Implementations: UiDispatcher (services/ui_dispatcher.py)
    """
    def post(self, callback: Callable[[], Any]) -> None:
        """Enqueue a callback to be executed on the UI thread.

        Args:
            callback: A zero-argument callable.
        """
        ...


class CleanerAppProtocol(Protocol):
    """Minimal host surface used by pages, not the whole application object.

    This Protocol defines the interface that pages expect from their
    host application (the "app" object passed to their __init__).

    Implementations: CleanerApp (app.py), MainWindow (ui/main_window.py)
    """

    # Attributes
    busy: bool
    categories: list[CleanCategoryProtocol]
    scanner: Any

    # Methods
    def confirm_clean(self) -> None:
        """Trigger the confirmation dialog and initiate cleaning."""
        ...

    def load_winapp_rules(self) -> None:
        """Load and parse the winapp2.ini file."""
        ...

    def preview_clean(self) -> None:
        """Collect preview file lists for selected categories."""
        ...

    def request_cancel(self) -> None:
        """Request cancellation of the current background operation."""
        ...

    def update_total(self) -> None:
        """Recalculate and display the total size/files to clean."""
        ...

    def log(self, msg: str) -> None:
        """Append a message to the application log.

        Args:
            msg: The log message string.
        """
        ...

    def set_status(self, text: str) -> None:
        """Update the status bar text.

        Args:
            text: The status message to display.
        """
        ...

    def set_busy(self, value: bool, mode: str = "determinate") -> None:
        """Set the application's busy state.

        Args:
            value: True to show busy state (progress bar), False to hide.
            mode: "determinate" (known progress) or "indeterminate" (unknown).
        """
        ...
