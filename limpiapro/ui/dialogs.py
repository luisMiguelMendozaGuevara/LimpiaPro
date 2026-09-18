"""Styled alert / confirmation dialogs and readonly text dialogs.

Replaces raw QMessageBox usage with theme-aware dialogs: themed side
icon, bold summary line and explicit buttons ("Si, limpiar" / "Cancelar")
instead of the generic Yes/No. The safe default is always Cancel.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import APP_NAME
from ..i18n import t

_GEOMETRY_RE = re.compile(r"(\d+)x(\d+)")

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

    Themed side icon, bold summary line, descriptive body and explicit
    buttons instead of the generic Yes/No. The safe default is Cancel.

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
