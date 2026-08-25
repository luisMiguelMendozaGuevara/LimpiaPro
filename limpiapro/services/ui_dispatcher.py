"""Thread-safe adapter around the application's UI callback queue.

This module provides a UI-agnostic interface for posting callbacks from
background threads to the main UI thread. It currently wraps the legacy
Tkinter polling mechanism, but can be extended to support Qt or other
frameworks in the future.

Design Principle:
    Background workers MUST NOT directly manipulate UI widgets or call
    Tkinter methods. They must post a callback through this dispatcher,
    which will be drained by the UI's main poller loop.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..ui.legacy_tk.widgets import post_ui, start_ui_poller


class UiDispatcher:
    """Publish callbacks to the queue drained by Tk's single UI poller.

    This class acts as a bridge between the multi-threaded business logic
    and the single-threaded Tkinter event loop. It ensures that all UI
    updates happen on the main thread, preventing race conditions and
    Tkinter's notorious "not thread-safe" crashes.

    Attributes:
        _queue: Reference to the underlying queue (managed by widgets.py).
    """

    def post(self, callback: Callable[[], Any]) -> None:
        """Enqueue a callback to be executed on the UI thread.

        Args:
            callback: A zero-argument callable. It will be invoked on the
                      main thread during the next poller cycle.
        """
        post_ui(callback)

    def start_poller(self, widget: Any, interval: int = 50) -> None:
        """Start the periodic poller that drains the callback queue.

        This must be called once during application startup, typically from
        the main window's __init__ method.

        Args:
            widget: A Tkinter widget (usually the root window) to schedule
                    the polling loop on.
            interval: Polling interval in milliseconds. Lower values give
                      more responsive UI updates but consume more CPU.
                      Default is 50ms (20 FPS).
        """
        start_ui_poller(widget, interval)
