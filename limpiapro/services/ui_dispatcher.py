"""Thread-safe adapter around the application's UI callback queue."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..ui.widgets import post_ui, start_ui_poller


class UiDispatcher:
    """Publish callbacks to the queue drained by Tk's single UI poller."""

    def post(self, callback: Callable[[], Any]) -> None:
        post_ui(callback)

    def start_poller(self, widget: Any, interval: int = 50) -> None:
        start_ui_poller(widget, interval)
