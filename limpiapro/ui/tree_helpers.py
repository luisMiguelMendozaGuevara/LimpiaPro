"""Tree helpers: make_tree / fill_tree / selected_* for QTreeWidget.

- make_tree(parent, spec)   -> QTreeWidget with the spec's columns
- fill_tree(tree, specs)    -> batched population (no UI freeze)
- selected_one/many(tree, data) -> entries of `data` for the selection
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QTreeWidget,
    QTreeWidgetItem,
)

from .. import APP_NAME
from ..i18n import t
from .constants import TREE_CHUNK
from .dialogs import app_info


def make_tree(parent, spec):
    """QTreeWidget with the column spec.

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


def fill_tree(tree, specs, chunk: int = TREE_CHUNK):
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
            item = QTreeWidgetItem([text, *list(values)])
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
