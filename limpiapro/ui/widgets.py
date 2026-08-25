"""Shared PySide6 widgets and helpers (replica of the legacy toolkit).

This module provides a set of reusable PySide6 widgets and utility functions
that replicate the behavior of the legacy CustomTkinter toolkit. It serves
as the bridge between the old UI paradigm and the new PySide6 implementation.

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

Design Principles:
1. Thread Safety: All UI updates are marshaled through Qt signals.
2. Performance: Tree population is batched to prevent UI freezing.
3. Compatibility: API mirrors the legacy toolkit for easy migration.
"""

from __future__ import annotations

import re
import threading

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
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
# MAINTAINABILITY: This global list prevents a notorious PySide6/PyQt bug
# where the signal source is garbage-collected while the C++ thread is
# still running, leading to segfaults or silent failures.
_ACTIVE: list = []

_GEOMETRY_RE = re.compile(r"(\d+)x(\d+)")


# ---------------------------------------------------------------------------
# Worker helper (run_async with a daemon thread + signal bridge)
# ---------------------------------------------------------------------------


class _Bridge(QObject):
    """Delivers the worker result/exception to the UI thread.

    This is a lightweight QObject that lives on the UI thread and acts
    as the signal source for the worker's completion or failure.
    """

    done = Signal(object)    # the worker's return value (usually a tuple)
    failed = Signal(object)  # the raised exception


def run_async(host, worker, done, args=(), on_error=None):
    """Run worker(*args) on a daemon thread; done(*result) or on_error(exc)
    run on the UI thread (same contract as the legacy run_async helper).

    This function is the primary mechanism for executing background work
    in the PySide6 UI. It ensures that:
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


# ---------------------------------------------------------------------------
# Tree helpers (replica of make_tree / fill_tree / selected_*)
# ---------------------------------------------------------------------------


def make_tree(parent, spec):
    """QTreeWidget with the legacy column spec.

    spec: list of (column_key, heading, width[, anchor]); the first entry
    describes the tree column (#0). Returns the tree widget.

    Args:
        parent: The parent QWidget.
        spec: A list of column specifications.

    Returns:
        QTreeWidget: A configured tree widget.
    """
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
    "open" (bool).

    Args:
        tree: The QTreeWidget to populate.
        specs: A list of row specifications.
        chunk: Number of rows to insert per batch (default 200).
    """
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
            # Schedule the next batch on the UI thread to prevent freezing.
            QTimer.singleShot(0, _flush)
    _flush()
    # Expand explicitly opened groups after the batch fill.
    for entry in specs:
        kw = entry[3] if len(entry) == 4 else entry[2]
        if kw.get("open") and kw.get("key") in parents:
            parents[kw["key"]].setExpanded(True)


def item_data(item: QTreeWidgetItem):
    """The UserRole payload of a tree item (index or path), or None.

    Args:
        item: The tree widget item.

    Returns:
        The data stored in Qt.UserRole, or None.
    """
    if item is None:
        return None
    return item.data(0, Qt.UserRole)


def selected_one(tree, data):
    """Entry of `data` for the tree's first selection, or None.

    Args:
        tree: The QTreeWidget.
        data: A list of data objects indexed by the item's UserRole index.

    Returns:
        The selected data object, or None if no selection or invalid.
    """
    items = tree.selectedItems()
    if not items:
        app_info(None, "info", APP_NAME, t("msg.select_one"))
        return None
    idx = item_data(items[0])
    if not isinstance(idx, int):
        app_info(None, "warning", APP_NAME, t("msg.select_one_error"))
        return None
    try:
        return data[idx]
    except (IndexError, TypeError):
        app_info(None, "warning", APP_NAME, t("msg.select_one_error"))
        return None


def selected_many(tree, data):
    """All entries of `data` matching the current selection.

    Args:
        tree: The QTreeWidget.
        data: A list of data objects indexed by the item's UserRole index.

    Returns:
        list: The selected data objects, or None if empty.
    """
    out = []
    for item in tree.selectedItems():
        idx = item_data(item)
        if isinstance(idx, int) and 0 <= idx < len(data):
            out.append(data[idx])
    if not out:
        app_info(None, "info", APP_NAME, t("msg.select_one"))
    return out or None


# ---------------------------------------------------------------------------
# Styled alert / confirmation dialogs
# ---------------------------------------------------------------------------

# kind -> (icon name, palette role) for the dialog's side icon.
_KIND_ART: dict[str, tuple[str, str]] = {
    "warning": ("shield", "warning"),
    "danger": ("delete", "error"),
    "critical": ("cancel", "error"),
    "info": ("preview", "accent"),
    "success": ("enable", "success"),
}


def _kind_pixmap(kind: str, size: int = 40):
    """The themed side icon for an alert dialog.

    Args:
        kind: One of _KIND_ART's keys.
        size: Logical pixel size.

    Returns:
        QPixmap: The rendered icon (info icon when kind is unknown).
    """
    from . import icons
    name, role = _KIND_ART.get(kind, _KIND_ART["info"])
    return icons.pixmap(name, size, role=role)


def _rich_message(message: str) -> str:
    """Render a plain message as rich text with a bold first line.

    The first line acts as the question/summary; the rest becomes the
    explanation block, which makes dialogs much easier to scan.

    Args:
        message: The plain-text message (may contain newlines).

    Returns:
        str: HTML with the first line bolded.
    """
    import html as _html
    parts = message.split("\n", 1)
    head = f"<b>{_html.escape(parts[0])}</b>"
    if len(parts) > 1 and parts[1].strip():
        return head + "<br>" + _html.escape(parts[1]).replace("\n", "<br>")
    return head


def app_confirm(parent, kind: str, title: str, message: str,
               yes_text: str | None = None,
               no_text: str | None = None) -> bool:
    """A styled yes/no confirmation dialog.

    Replaces QMessageBox.question: themed side icon, bold summary line,
    descriptive body and explicit buttons ("Sí, eliminar" / "Cancelar")
    instead of the generic Yes/No. The safe default is Cancel.

    Args:
        parent: Owner widget (may be None).
        kind: "warning" or "danger" (drives the icon).
        title: Dialog window title.
        message: The explanation (first line is bolded).
        yes_text: Optional label for the confirm button.
        no_text: Optional label for the cancel button.

    Returns:
        bool: True when the user accepted.
    """
    box = QMessageBox(parent)
    box.setWindowTitle(title or APP_NAME)
    box.setIconPixmap(_kind_pixmap(kind))
    box.setTextFormat(Qt.RichText)
    box.setText(_rich_message(message))
    yes = box.addButton(yes_text or t("btn.confirm_yes"),
                        QMessageBox.ButtonRole.YesRole)
    no = box.addButton(no_text or t("btn.cancel"),
                       QMessageBox.ButtonRole.NoRole)
    yes.setProperty("kind", "primary")
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes


def structured_confirm(parent, kind: str, heading: str, subtitle: str,
                       items, notes=(), yes_text: str | None = None) -> bool:
    """A structured confirmation dialog with real layout hierarchy.

    Renders: side icon + heading + subtitle, an item list (each row with a
    right-aligned detail such as its size), highlighted note cards for the
    recommendations and explicit primary/cancel buttons (safe default).

    Args:
        parent: Owner widget (may be None).
        kind: "warning" or "danger" (drives icon and note-card colors).
        heading: The main question, e.g. "3 categories will be cleaned".
        subtitle: One-line context under the heading.
        items: Iterable of (text, right_label) tuples.
        notes: Iterable of note strings shown in highlighted cards.
        yes_text: Optional label for the confirm button.

    Returns:
        bool: True when the user accepted.
    """
    from PySide6.QtWidgets import QFrame, QHBoxLayout

    dlg = QDialog(parent)
    dlg.setWindowTitle(APP_NAME)
    dlg.setMinimumWidth(480)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(24, 20, 24, 20)
    lay.setSpacing(12)

    head = QHBoxLayout()
    head.setSpacing(14)
    icon_lbl = QLabel()
    icon_lbl.setPixmap(_kind_pixmap(kind, 44))
    icon_lbl.setFixedWidth(48)
    icon_lbl.setAlignment(Qt.AlignTop)
    head.addWidget(icon_lbl)
    head_col = QVBoxLayout()
    head_col.setSpacing(4)
    h_lbl = QLabel(heading)
    h_lbl.setObjectName("dlgHeading")
    h_lbl.setWordWrap(True)
    head_col.addWidget(h_lbl)
    s_lbl = QLabel(subtitle)
    s_lbl.setObjectName("dlgSubtle")
    s_lbl.setWordWrap(True)
    head_col.addWidget(s_lbl)
    head.addLayout(head_col, 1)
    lay.addLayout(head)

    if items:
        list_host = QWidget()
        rows = QVBoxLayout(list_host)
        rows.setContentsMargins(62, 0, 0, 0)
        rows.setSpacing(5)
        for text, right in items:
            row = QHBoxLayout()
            row.setSpacing(8)
            name_lbl = QLabel(text)
            name_lbl.setObjectName("dlgItem")
            row.addWidget(name_lbl, 1)
            if right:
                size_lbl = QLabel(right)
                size_lbl.setObjectName("dlgItemRight")
                row.addWidget(size_lbl)
            rows.addLayout(row)
        lay.addWidget(list_host)

    for note in notes:
        card = QFrame()
        card.setObjectName("noteCard")
        card.setProperty("kind", kind)
        card_lay = QHBoxLayout(card)
        card_lay.setContentsMargins(12, 9, 12, 9)
        note_lbl = QLabel(note)
        note_lbl.setObjectName("noteText")
        note_lbl.setWordWrap(True)
        card_lay.addWidget(note_lbl)
        lay.addWidget(card)

    buttons = QHBoxLayout()
    buttons.setSpacing(8)
    buttons.addStretch(1)
    no = QPushButton(t("btn.cancel"))
    no.setDefault(True)
    no.clicked.connect(dlg.reject)
    yes = QPushButton(yes_text or t("btn.confirm_yes"))
    yes.setProperty("kind", "primary")
    yes.clicked.connect(dlg.accept)
    buttons.addWidget(no)
    buttons.addWidget(yes)
    lay.addLayout(buttons)

    return dlg.exec() == QDialog.DialogCode.Accepted


def app_info(parent, kind: str, title: str, message: str) -> None:
    """A styled one-button notification dialog (info/warning/critical).

    Args:
        parent: Owner widget (may be None).
        kind: "info", "warning", "critical" or "success".
        title: Dialog window title.
        message: The explanation (first line is bolded).
    """
    box = QMessageBox(parent)
    box.setWindowTitle(title or APP_NAME)
    box.setIconPixmap(_kind_pixmap(kind))
    box.setTextFormat(Qt.RichText)
    box.setText(_rich_message(message))
    accept = box.addButton(t("btn.accept"),
                           QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(accept)
    box.exec()


# ---------------------------------------------------------------------------
# Readonly console / dialogs
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Empty state placeholder
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Flow layout (wrapping toolbar)
# ---------------------------------------------------------------------------


class FlowLayout(QLayout):
    """Toolbar layout that wraps widgets to the next line when they do
    not fit, so button text is never clipped on narrow windows.

    Args:
        parent: The parent widget.
        spacing: Horizontal and vertical gap between items (default 8).
    """

    def __init__(self, parent: QWidget | None = None, spacing: int = 8):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self._spacing = spacing
        self._items: list = []

    def addItem(self, item) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        line_height = 0
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            next_x = x + w + self._spacing
            if next_x - self._spacing > right and line_height > 0:
                x = rect.x() + m.left()
                y = y + line_height + self._spacing
                next_x = x + w + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), QSize(w, h)))
            x = next_x
            line_height = max(line_height, h)
        return y + line_height - rect.y() + m.bottom()


class EmptyState(QWidget):
    """Centered icon + muted-text placeholder shown when a list is empty.

    Attributes:
        icon_lbl: The QLabel holding the themed icon pixmap.
        text_lbl: The muted description label.
    """

    def __init__(self, icon_name: str, text: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._icon_name = icon_name
        lay = QVBoxLayout(self)
        lay.addStretch(1)
        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.icon_lbl)
        self.text_lbl = QLabel(text)
        self.text_lbl.setObjectName("pageSubtitle")
        self.text_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.text_lbl)
        lay.addStretch(1)
        self.refresh_icon()

    def refresh_icon(self) -> None:
        """Re-render the pixmap (after a dark/light switch)."""
        from . import icons
        pm = icons.pixmap(self._icon_name, 44, role="faint")
        self.icon_lbl.setPixmap(pm)


def readonly_scrolled(parent):
    """Readonly monospace textbox inside a plain frame.
    Returns (frame, box); the box must be written with setReadOnly(False).

    Args:
        parent: The parent QWidget.

    Returns:
        tuple: (frame: QWidget, box: QPlainTextEdit).
    """
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
    Returns (win, box).

    Args:
        master: The parent QWidget.
        title: The window title.
        geometry: Window geometry string (e.g., "760x520").
        header: Optional header text.

    Returns:
        tuple: (win: QDialog, box: QPlainTextEdit).
    """
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
    """Destructive-action confirmation dialog. Returns True/False.

    Args:
        title: Dialog title.
        details: Main message text.
        extra: Optional additional warning text.

    Returns:
        bool: True if the user clicked Yes, False otherwise.
    """
    msg = (f"{details}\n\n{extra}\n{t('ui.continue_q')}" if extra
           else f"{details}\n\n{t('ui.continue_q')}")
    return QMessageBox.question(
        None, title or APP_NAME, msg,
        QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes
