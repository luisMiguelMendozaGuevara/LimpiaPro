"""Background-worker helper: run a callable off the UI thread.

Worker threads never touch Qt widgets directly. run_async executes the
worker on a daemon thread and marshals the result back through a queued
signal, so the done/on_error callbacks always run on the UI thread. Daemon
threads also mean a long scan left running at exit cannot abort the
process (the old QThread variant destroyed the thread object while its
thread was still running and Qt failed fast).
"""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal

from ..utils import _errlog

# Keep bridge objects alive until their thread delivers the result:
# dropping the Python reference earlier lets GC delete the signal source
# while the worker is still emitting.
# MAINTAINABILITY: This global list prevents a notorious PySide6/PyQt bug
# where the signal source is garbage-collected while the C++ thread is
# still running, leading to segfaults or silent failures.
_ACTIVE: list = []


class _Bridge(QObject):
    """Delivers the worker result/exception to the UI thread.

    This is a lightweight QObject that lives on the UI thread and acts
    as the signal source for the worker's completion or failure.
    """

    done = Signal(object)    # the worker's return value (usually a tuple)
    failed = Signal(object)  # the raised exception


def run_async(host, worker, done, args=(), on_error=None):
    """Run worker(*args) on a daemon thread; done(*result) or on_error(exc)
    run on the UI thread.

    This is the primary mechanism for executing background work in the
    PySide6 UI:
    1. The worker runs on a separate thread (no UI blocking).
    2. The result callbacks run on the UI thread (thread-safe UI updates).
    3. Exceptions in the worker are caught and delivered to on_error.

    Args:
        host: The host widget (unused, kept for API compatibility).
        worker: A callable to execute on the background thread.
        done: A callback to invoke on the UI thread with the worker's result.
        args: Positional arguments to pass to the worker.
        on_error: Optional callback to invoke on the UI thread if the
                  worker raises an exception.
    """
    bridge = _Bridge()

    def _finish(result):
        if bridge in _ACTIVE:
            _ACTIVE.remove(bridge)
        try:
            if isinstance(result, tuple):
                done(*result)
            else:
                done(result)
        except Exception as e:
            _errlog(f"run_async done callback failed: {e!r}")

    def _fail(exc):
        if bridge in _ACTIVE:
            _ACTIVE.remove(bridge)
        if on_error is not None:
            try:
                on_error(exc)
            except Exception as e:
                _errlog(f"run_async on_error callback failed: {e!r}")

    bridge.done.connect(_finish)
    bridge.failed.connect(_fail)
    _ACTIVE.append(bridge)

    def _thread():
        try:
            result = worker(*args)
        except Exception as e:  # never let a worker die silently
            bridge.failed.emit(e)
            return
        bridge.done.emit(result)

    threading.Thread(target=_thread, daemon=True).start()
