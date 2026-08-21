"""Shared UI widgets and helpers.

Threading model: worker threads never touch tkinter directly. run_async
executes the worker on a daemon thread and marshals the result back through
a thread-safe queue that a single poller (start_ui_poller) drains on the UI
thread. tkinter does not guarantee widget.after() from secondary threads,
which is why every thread -> UI hop goes through post_ui."""

import queue
import threading
from tkinter import messagebox, ttk

import customtkinter as ctk

from ... import APP_NAME
from ...i18n import t
from ...utils import _errlog

# Thread-safe queue used to run callbacks on the UI thread. A single
# poller drains it; see start_ui_poller.
_UI_QUEUE = queue.Queue()


def post_ui(fn):
    """Schedule `fn` to run on the UI thread (thread-safe)."""
    _UI_QUEUE.put(fn)


def start_ui_poller(widget, interval=50):
    """Start the single post_ui poller on `widget`.

    Every `interval` ms the queue is drained (callbacks run on the UI
    thread) and the poller reschedules itself. Callback exceptions are
    logged instead of killing the poller loop."""
    def _poll():
        try:
            while True:
                fn = _UI_QUEUE.get_nowait()
                try:
                    fn()
                except Exception as e:
                    _errlog(f"UI callback failed: {e!r}")
        except queue.Empty:
            pass
        try:
            widget.after(interval, _poll)
        except Exception:
            pass  # nosec B110 - poll re-arming is best-effort
    widget.after(interval, _poll)


def run_async(widget, worker, done, args=(), on_error=None):
    """Run worker(*args) on a thread and call done(*result) on the UI.

    Contract: the worker returns the tuple of arguments for done. If the
    worker raises, the error is logged and on_error(e) is invoked (on the
    UI thread) when provided, so the caller can undo its busy state and
    surface the failure."""
    def _thread():
        try:
            result = worker(*args)
        except Exception as e:
            _errlog(f"worker failed ({getattr(worker, '__name__', worker)}): {e!r}")
            if on_error is not None:
                # Capture `e` as a default argument: the `except` clause
                # deletes the exception variable when the block ends, and
                # the lambda scheduled for the UI runs later.
                handler = on_error
                post_ui(lambda e=e: handler(e))
            return
        post_ui(lambda: done(*result))
    threading.Thread(target=_thread, daemon=True).start()


def make_tree(parent, spec, style="Dup.Treeview"):
    """Treeview + vertical scrollbar with the shared style.

    spec: list of (column, heading, width[, anchor]); the first entry
    describes the tree column (#0). Returns the treeview."""
    cols = tuple(s[0] for s in spec[1:])
    tree = ttk.Treeview(parent, columns=cols, show="tree", style=style)
    tree.heading("#0", text=spec[0][1])
    tree.column("#0", width=spec[0][2])
    for col, head, width, *rest in spec[1:]:
        anchor = rest[0] if rest else "w"
        tree.heading(col, text=head)
        tree.column(col, width=width, anchor=anchor)
    sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=4)
    sb.pack(side="right", fill="y", pady=4)
    return tree


def fill_tree(tree, specs, chunk=200):
    """Populate a Treeview in batches (thousands of row-by-row inserts
    would freeze the UI).

    `specs` is a list of tuples (iid, parent, text, values, kw):
      - iid: item identifier ('' lets ttk assign one; selected_one /
        selected_many use it as an index into the data list).
      - parent: iid of the parent item, or '' for root.
      - kw: optional dict (tags, image, open, ...).
    Preserves the integer-iid scheme used by selected_one/selected_many."""
    tree.delete(*tree.get_children())
    total = len(specs)
    if not total:
        return
    idx = 0

    def _flush():
        nonlocal idx
        end = min(idx + chunk, total)
        for i in range(idx, end):
            entry = specs[i]
            iid, parent, text, values, *rest = entry
            kw = rest[0] if rest else {}
            tree.insert(parent, "end", iid=iid or None, text=text,
                        values=values, **kw)
        idx = end
        if idx < total:
            try:
                tree.after(1, _flush)
            except Exception:
                _flush()
    _flush()


def selected_one(tree, data):
    """Entry of `data` for the tree's selection, or None.

    Robust against refreshes that desynchronize the tree iids."""
    sel = tree.selection()
    if not sel:
        messagebox.showinfo(APP_NAME, t("msg.select_one"))
        return None
    try:
        return data[int(sel[0])]
    except (ValueError, IndexError):
        messagebox.showerror(
            APP_NAME, t("msg.select_one_error"))
        return None


def selected_many(tree, data):
    """Like selected_one but with the complete multi-selection."""
    sel = tree.selection()
    if not sel:
        messagebox.showinfo(APP_NAME, t("msg.select_one"))
        return None
    try:
        return [data[int(iid)] for iid in sel]
    except (ValueError, IndexError):
        messagebox.showerror(
            APP_NAME, t("msg.select_many_error"))
        return None


def readonly_scrolled(parent):
    """Readonly monospace textbox inside a transparent frame.
    Returns (frame, box); the box must be written with state='normal'."""
    frame = ctk.CTkFrame(parent, fg_color="transparent")
    box = ctk.CTkTextbox(frame, font=ctk.CTkFont(family="Consolas", size=11))
    box.pack(side="left", fill="both", expand=True)
    box.configure(state="disabled")
    return frame, box


def readonly_toplevel(master, title, geometry, header=None):
    """Toplevel window with optional header and a readonly textbox.
    Returns (win, box)."""
    win = ctk.CTkToplevel(master)
    win.title(title)
    win.geometry(geometry)
    if header:
        ctk.CTkLabel(win, text=header, font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=("gray30", "gray70")).pack(anchor="w", padx=14, pady=(10, 2))
    frame, box = readonly_scrolled(win)
    frame.pack(fill="both", expand=True, padx=14, pady=6)
    return win, box


def confirm_destructive(title, details, extra=""):
    """Destructive-action confirmation dialog. Returns True/False."""
    msg = (f"{details}\n\n{extra}\n{t('ui.continue_q')}" if extra
           else f"{details}\n\n{t('ui.continue_q')}")
    return messagebox.askyesno(APP_NAME, msg, icon="warning")
