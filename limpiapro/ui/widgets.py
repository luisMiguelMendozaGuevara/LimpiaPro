"""Shared PySide6 widgets and helpers (replica of the legacy toolkit).

Threading model: worker threads never touch Qt widgets directly.
run_async executes the worker on a daemon thread and marshals the result
back through a queued signal, so the done/on_error callbacks always run
on the UI thread (the same contract the legacy pages used). Daemon
threads also mean a long scan left running at exit cannot abort the
process (the old QThread variant destroyed the thread object while its
thread was still running and Qt failed fast).

Tree helpers mirror the legacy make_tree/fill_tree/selected_* API:
  - make_tree(parent, spec)   -> QTreeWidget with the spec's columns
  - fill_tree(tree, specs)    -> batched population (no UI freeze)
  - selected_one/many(tree, data) -> entries of `data` for the selection
"""

from __future__ import annotations

import re
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..i18n import t
from ..utils import _errlog

# Keep bridge objects alive until their thread delivers the result:
# dropping the Python reference earlier lets GC delete the signal source
# while the worker is still emitting.
_ACTIVE: list = []

_GEOMETRY_RE = re.compile(r"(\d+)x(\d+)")


# ---------------------------------------------------------------------------
# Worker helper (run_async with a daemon thread + signal bridge)
# ---------------------------------------------------------------------------


class _Bridge(QObject):
    """Delivers the worker result/exception to the UI thread."""

    done = Signal(object)    # the worker's return value (usually a tuple)
    failed = Signal(object)  # the raised exception


def run_async(host, worker, done, args=(), on_error=None):
    """Run worker(*args) on a daemon thread; done(*result) or on_error(exc)
    run on the UI thread (same contract as the legacy run_async helper)."""
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


# ---------------------------------------------------------------------------
# Tree helpers (replica of make_tree / fill_tree / selected_*)
# ---------------------------------------------------------------------------


def make_tree(parent, spec):
    """QTreeWidget with the legacy column spec.

    spec: list of (column_key, heading, width[, anchor]); the first entry
    describes the tree column (#0). Returns the tree widget."""
    tree = QTreeWidget(parent)
    tree.setColumnCount(len(spec))
    tree.setHeaderLabels([s[1] for s in spec])
    for i, s in enumerate(spec):
        tree.setColumnWidth(i, s[2])
        if len(s) > 3 and s[3] in ("center", "e"):
            align = Qt.AlignCenter if s[3] == "center" \
                else Qt.AlignRight | Qt.AlignVCenter
            tree.headerItem().setTextAlignment(i, align)
    tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
    tree.setAlternatingRowColors(True)
    tree.setRootIsDecorated(True)
    return tree


def fill_tree(tree, specs, chunk=200):
    """Populate the tree in batches (thousands of row-by-row inserts
    would freeze the UI).

    `specs` is a list of tuples:
      (text, values, kw)             -> a top-level row
      (parent_key, text, values, kw) -> a child of the top-level row whose
                                        kw["key"] equals parent_key
    kw supports: "key" (item key, for children), "index" (int stored as
    UserRole for selected_one/many), "path" (str stored as UserRole, used
    by the duplicates page), "fg" (hex text color), "icon" (QIcon),
    "open" (bool)."""
    tree.clear()
    total = len(specs)
    if not total:
        return
    idx = 0
    parents: dict[str, QTreeWidgetItem] = {}

    def _flush():
        nonlocal idx
        end = min(idx + chunk, total)
        for i in range(idx, end):
            entry = specs[i]
            if len(entry) == 3:
                text, values, kw = entry
                parent_key = ""
            else:
                parent_key, text, values, kw = entry
            item = QTreeWidgetItem([text] + list(values))
            if kw.get("index") is not None:
                item.setData(0, Qt.UserRole, kw["index"])
            elif kw.get("path") is not None:
                item.setData(0, Qt.UserRole, kw["path"])
            fg = kw.get("fg")
            if fg:
                item.setForeground(0, QBrush(QColor(fg)))
            icon = kw.get("icon")
            if icon is not None:
                item.setIcon(0, icon)
            key = kw.get("key")
            if parent_key:
                parent = parents.get(parent_key)
                if parent is not None:
                    parent.addChild(item)
            else:
                tree.addTopLevelItem(item)
            if key is not None:
                parents[key] = item
        idx = end
        if idx < total:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, _flush)
    _flush()
    # Expand explicitly opened groups after the batch fill.
    for entry in specs:
        kw = entry[3] if len(entry) == 4 else entry[2]
        if kw.get("open") and kw.get("key") in parents:
            parents[kw["key"]].setExpanded(True)


def item_data(item: QTreeWidgetItem):
    """The UserRole payload of a tree item (index or path), or None."""
    if item is None:
        return None
    return item.data(0, Qt.UserRole)


def selected_one(tree, data):
    """Entry of `data` for the tree's first selection, or None."""
    items = tree.selectedItems()
    if not items:
        QMessageBox.information(None, APP_NAME, t("msg.select_one"))
        return None
    idx = item_data(items[0])
    if not isinstance(idx, int):
        QMessageBox.warning(None, APP_NAME, t("msg.select_one_error"))
        return None
    try:
        return data[idx]
    except (IndexError, TypeError):
        QMessageBox.warning(None, APP_NAME, t("msg.select_one_error"))
        return None


def selected_many(tree, data):
    """All entries of `data` matching the current selection."""
    out = []
    for item in tree.selectedItems():
        idx = item_data(item)
        if isinstance(idx, int) and 0 <= idx < len(data):
            out.append(data[idx])
    if not out:
        QMessageBox.information(None, APP_NAME, t("msg.select_one"))
    return out or None


# ---------------------------------------------------------------------------
# Readonly console / dialogs
# ---------------------------------------------------------------------------


def readonly_scrolled(parent):
    """Readonly monospace textbox inside a plain frame.
    Returns (frame, box); the box must be written with setReadOnly(False)."""
    frame = QWidget(parent)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(0, 0, 0, 0)
    box = QPlainTextEdit(frame)
    box.setReadOnly(True)
    box.setLineWrapMode(QPlainTextEdit.WidgetWidth)
    lay.addWidget(box)
    return frame, box


def readonly_toplevel(master, title, geometry, header=None):
    """Modal dialog with an optional header and a readonly textbox.
    Returns (win, box)."""
    win = QDialog(master)
    win.setWindowTitle(title)
    m = _GEOMETRY_RE.match(geometry)
    if m:
        win.resize(int(m.group(1)), int(m.group(2)))
    lay = QVBoxLayout(win)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    if header:
        lbl = QLabel(header)
        lbl.setObjectName("pageTitle")
        lay.addWidget(lbl)
    frame, box = readonly_scrolled(win)
    lay.addWidget(frame, 1)
    close = QPushButton(t("btn.cancel"))
    close.clicked.connect(win.accept)
    h = QHBoxLayout()
    h.addStretch(1)
    h.addWidget(close)
    lay.addLayout(h)
    return win, box


def confirm_destructive(title, details, extra=""):
    """Destructive-action confirmation dialog. Returns True/False."""
    msg = (f"{details}\n\n{extra}\n{t('ui.continue_q')}" if extra
           else f"{details}\n\n{t('ui.continue_q')}")
    return QMessageBox.question(
        None, title or APP_NAME, msg,
        QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes
