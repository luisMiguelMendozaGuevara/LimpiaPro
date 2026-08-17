"""Tests for the run_async/post_ui contract without a real Tk window.

No window is created; _UI_QUEUE is drained manually (or post_ui is
monkeypatched) to isolate the callback-scheduling logic."""

import time

import pytest

from limpiapro.ui import widgets


@pytest.fixture(autouse=True)
def _clean_queue():
    """run_async threads can leave residues in the queue."""
    while True:
        try:
            widgets._UI_QUEUE.get_nowait()
        except Exception:
            break
    yield
    while True:
        try:
            widgets._UI_QUEUE.get_nowait()
        except Exception:
            break


def _drain_queue():
    """Run every pending UI callback on this thread."""
    while True:
        try:
            fn = widgets._UI_QUEUE.get_nowait()
        except Exception:
            return
        fn()


def test_post_ui_enqueues_through_the_queue():
    received = []
    widgets.post_ui(lambda: received.append("a"))
    widgets.post_ui(lambda: received.append("b"))
    assert received == []  # nothing drained yet
    _drain_queue()
    assert received == ["a", "b"]


def _wait(cond, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_run_async_worker_ok_calls_done_with_tuple():
    results = []

    def worker(a, b):
        return a + b, a * b

    def done(total, product):
        results.append((total, product))

    widgets.run_async(None, worker, done, args=(3, 4))
    assert _wait(lambda: widgets._UI_QUEUE.qsize() >= 1)
    _drain_queue()
    assert _wait(lambda: results)
    assert results == [(7, 12)]


def test_run_async_worker_error_posts_on_error(monkeypatch):
    errors = []
    done_calls = []
    monkeypatch.setattr(widgets, "_errlog", lambda msg: None)

    def worker():
        raise ValueError("internal failure")

    def done(*_a):
        done_calls.append(1)

    def on_error(e):
        errors.append(e)

    widgets.run_async(None, worker, done, on_error=on_error)
    assert _wait(lambda: widgets._UI_QUEUE.qsize() >= 1)
    _drain_queue()
    assert _wait(lambda: errors)
    assert len(done_calls) == 0  # done is NOT invoked when the worker failed
    assert isinstance(errors[0], ValueError)


def test_run_async_no_on_error_leaves_queue_empty(monkeypatch):
    logs = []
    monkeypatch.setattr(widgets, "_errlog", lambda msg: logs.append(msg))

    def worker():
        raise ValueError("no on_error")

    widgets.run_async(None, worker, lambda: None)
    # The worker will blow up and, with no on_error, the queue stays
    # callback-free: only the error log entry should appear.
    assert _wait(lambda: logs)
    assert "worker failed" in logs[0]
    assert widgets._UI_QUEUE.empty()


def test_start_ui_poller_drains_on_interval():
    executed = []
    pending = []

    class _FakeWidget:
        def after(self, _ms, fn=None):
            pending.append(fn)

    widgets.post_ui(lambda: executed.append("echo"))
    widgets.start_ui_poller(_FakeWidget(), interval=0)
    # The poller schedules its tick via after(); we run it manually
    # (the fake does not run callbacks on its own, avoiding recursion).
    assert _wait(lambda: pending)
    pending.pop()()          # first _poll
    assert "echo" in executed
    assert pending            # the poller rescheduled itself
