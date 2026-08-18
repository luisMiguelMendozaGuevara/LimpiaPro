"""Structural contracts shared by pages and application services."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class CacheStore(Protocol):
    def load(self) -> dict[str, Any]: ...

    def save(self, data: dict[str, dict[str, int]], platform_name: str) -> None: ...


class CleanCategoryProtocol(Protocol):
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
    ) -> int: ...

    def list_files(self, limit: int = 1000) -> tuple[list[str], int]: ...

    def clean(
        self,
        target_bytes: int = 0,
        on_progress: Callable[[float], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[int, int, int]: ...

    def error_summary(self) -> dict[str, int]: ...


class UiDispatcherProtocol(Protocol):
    def post(self, callback: Callable[[], Any]) -> None: ...


class CleanerAppProtocol(Protocol):
    """Minimal host surface used by pages, not the whole application object."""

    busy: bool
    categories: list[CleanCategoryProtocol]
    scanner: Any

    def confirm_clean(self) -> None: ...
    def load_winapp_rules(self) -> None: ...
    def preview_clean(self) -> None: ...
    def request_cancel(self) -> None: ...
    def update_total(self) -> None: ...
    def log(self, msg: str) -> None: ...
    def set_status(self, text: str) -> None: ...
    def set_busy(self, value: bool, mode: str = "determinate") -> None: ...
