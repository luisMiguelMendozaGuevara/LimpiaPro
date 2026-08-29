"""Page: duplicate files finder 

This module implements the duplicate file scanner UI for PySide6. It
replicates the behavior of the legacy CustomTkinter duplicates page while
providing a modern, native Windows experience.

Architecture:
    - Drives DuplicateScanner on a worker thread.
    - The user picks a folder and a minimum size.
    - Results are shown as tree groups (one "original" plus its copies).
    - Selected copies get deleted after confirmation.
    - Each file row carries its path as UserRole data so deletion never
      relies on the displayed tree text.

Design Principles:
1. Safety: Deletion re-validates each file against the scan snapshot
   (size + mtime) to prevent deleting modified files.
2. Thread Safety: All scanner work happens on a background thread.
3. User Control: The user explicitly selects which copies to delete.
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ... import APP_NAME
from ...duplicates import DuplicateScanner
from ...i18n import t
from ...utils import _delete_path, _safe_size, format_size
from .. import icons
from ..dialogs import app_confirm, app_info
from ..empty_state import EmptyState
from ..tree_helpers import fill_tree, item_data, make_tree
from ..workers import run_async


class DuplicatePage(QWidget):
    """Duplicate file scanner page: folder picker, scan and delete.

    Attributes:
        host: The main window host.
        scanner: The DuplicateScanner instance (owned by host).
        tree: The QTreeWidget displaying duplicate groups.
    """

    def __init__(self, host, parent: QWidget | None = None):
        super().__init__(parent)
        self.host = host

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 8)
        lay.setSpacing(8)

        title = QLabel(t("dupes.title"))
        title.setObjectName("pageTitle")
        lay.addWidget(title)
        subtitle = QLabel(t("dupes.subtitle"))
        subtitle.setObjectName("pageSubtitle")
        lay.addWidget(subtitle)

        # ----------------------------------------------------------- bar
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.choose_btn = QPushButton(t("btn.choose_folder"))
        self.choose_btn.clicked.connect(self.choose_folder)
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText(t("dupes.path_placeholder"))
        self.min_combo = QComboBox()
        self.min_combo.addItems(["1 MB", "2 MB", "5 MB", "10 MB", "50 MB"])
        self.min_combo.setCurrentText("2 MB")
        self.scan_btn = QPushButton(t("btn.find_dupes"))
        self.scan_btn.setProperty("kind", "success")
        self.scan_btn.clicked.connect(self.start_scan)
        bar.addWidget(self.choose_btn)
        bar.addWidget(self.folder_edit, 1)
        bar.addWidget(QLabel(t("dupes.min_size")))
        bar.addWidget(self.min_combo)
        bar.addWidget(self.scan_btn)
        lay.addLayout(bar)

        self.info = QLabel("")
        self.info.setObjectName("mutedText")
        lay.addWidget(self.info)

        # ---------------------------------------------------------- tree
        self.tree = make_tree(
            self,
            [
                ("#0", t("col.file_group"), 560),
                ("dup", t("col.copies"), 70, "center"),
                ("size", t("col.size"), 90, "e"),
            ],
        )
        # Empty-state placeholder until the first scan finds groups.
        self._empty = EmptyState("dupes", t("dupes.subtitle"))
        self._tree_stack = QStackedWidget()
        self._tree_stack.addWidget(self._empty)
        self._tree_stack.addWidget(self.tree)
        lay.addWidget(self._tree_stack, 1)

        # --------------------------------------------------------- bottom
        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        help_lbl = QLabel(t("dupes.help", btn=t("btn.delete_selected")))
        help_lbl.setObjectName("mutedText")
        self.summary = QLabel("")
        self.summary.setObjectName("pageTitle")
        self.summary.setStyleSheet("font-size: 12px;")
        self.delete_btn = QPushButton(t("btn.delete_selected"))
        self.delete_btn.setProperty("kind", "danger")
        self.delete_btn.clicked.connect(self.delete_selected)
        bottom.addWidget(help_lbl)
        bottom.addWidget(self.summary)
        bottom.addStretch(1)
        bottom.addWidget(self.delete_btn)
        lay.addLayout(bottom)
        self._apply_button_icons()

    # ------------------------------------------------------------- state

    def _apply_button_icons(self) -> None:
        """Attach themed icons to the page buttons."""
        icons.apply(self.choose_btn, "folder")
        icons.apply(self.scan_btn, "scan", role="on_accent")
        icons.apply(self.delete_btn, "delete", role="error")

    def refresh_icons(self) -> None:
        """Re-apply every icon after a dark/light theme switch."""
        self._apply_button_icons()
        self._empty.refresh_icon()

    def on_busy(self, busy: bool) -> None:
        """Disable action buttons while an operation is running."""
        self.scan_btn.setEnabled(not busy)
        self.delete_btn.setEnabled(not busy)

    def on_show(self) -> None:
        """Called when the page becomes visible."""
        pass

    # ---------------------------------------------------------- actions

    def choose_folder(self) -> None:
        """Open a folder picker dialog."""
        path = QFileDialog.getExistingDirectory(self, t("dialog.pick_folder"))
        if path:
            self.folder_edit.setText(path)

    def start_scan(self) -> None:
        """Initiate the duplicate scan on a background thread."""
        if self.host.busy:
            return
        folder = self.folder_edit.text().strip()
        if not folder:
            app_info(self, "info", APP_NAME, t("msg.dupes_no_folder"))
            return
        min_mb = int(self.min_combo.currentText().split()[0])
        self.host.set_status(t("status.dupes_scanning", folder=folder))
        self.host.set_busy(True, mode="indeterminate")
        self.host.scanner = DuplicateScanner(folder, min_mb)
        self.tree.clear()
        self.summary.setText(t("label.scanning"))
        self.info.setText("")
        run_async(self, self._scan_worker, self._done, (folder,),
                  on_error=self._scan_error)

    def _scan_worker(self, folder):
        """Run the scanner phases (size -> prehash -> full hash).
        Returns (groups, None); the second slot is kept for symmetry."""
        return self.host.scanner.scan(), None

    def _scan_error(self, exc) -> None:
        """Handle scan errors."""
        self.host.set_busy(False)
        self.summary.setText("")
        self.host.set_status(t("status.dupes_failed"))
        self.host.log(t("log.dupes_error", exc=exc))
        app_info(self, "critical", APP_NAME, t("msg.error_simple", exc=exc))

    def _done(self, groups, error) -> None:
        """Handle scan completion."""
        self.host.set_busy(False)
        if error:
            self.summary.setText("")
            self.host.set_status(t("status.dupes_failed"))
            self.host.log(t("log.dupes_error", exc=error))
            app_info(self, "critical", APP_NAME,
                     t("msg.error_simple", exc=error))
            return
        self.tree.clear()
        if not groups:
            self.host.set_status(t("status.dupes_none"))
            self.summary.setText(t("dupes.none_found"))
            self.info.setText("")
            self._tree_stack.setCurrentWidget(self._empty)
            return
        self._tree_stack.setCurrentWidget(self.tree)
        dup_count = sum(len(g) - 1 for g in groups)
        wasted = sum(_safe_size(g[0]) * (len(g) - 1) for g in groups)
        self.summary.setText(
            t("dupes.summary", n=len(groups), size=format_size(wasted)))
        info = t("dupes.results_of", folder=self.folder_edit.text())
        skipped = getattr(self.host.scanner, "skipped", 0)
        if skipped:
            info += " " + t("dupes.unreadable", n=skipped)
        self.info.setText(info)
        specs = []
        for gi, group in enumerate(groups):
            gid = f"g{gi}"
            head = t("dupes.group_head",
                     name=os.path.basename(group[0]),
                     size=format_size(_safe_size(group[0])))
            specs.append((head, (str(len(group)), ""),
                          {"key": gid, "open": False}))
            specs.append((gid, t("dupes.original"), ("", ""), {}))
            specs.extend((gid, dup, ("", ""), {"path": dup})
                         for dup in group[1:])
        fill_tree(self.tree, specs)
        self.host.set_status(t("status.dupes_done", n=len(groups)))
        self.host.log(t("log.dupes_done", folder=self.folder_edit.text(),
                        n=len(groups), m=dup_count,
                        size=format_size(wasted)))

    def delete_selected(self) -> None:
        """Delete the selected duplicate files after confirmation."""
        paths = [p for p in (item_data(i) for i in self.tree.selectedItems())
                 if isinstance(p, str)]
        if not paths:
            app_info(self, "info", APP_NAME, t("msg.dupes_select"))
            return
        msg = t("msg.delete_files_header") + "\n".join(paths[:15])
        if len(paths) > 15:
            msg += "\n" + t("msg.and_n_more", n=len(paths) - 15)
        msg += ("\n\n"
                + t("msg.space_to_free",
                    size=format_size(sum(_safe_size(p) for p in paths)))
                + "\n\n" + t("ui.continue_q"))
        if not app_confirm(self, "danger", APP_NAME, msg,
                           yes_text=t("btn.delete_yes")):
            return
        self.host.set_busy(True, mode="indeterminate")
        snapshot = dict(getattr(self.host.scanner, "snapshot", {}))
        run_async(self, self._delete_worker, self._delete_done,
                  (paths, snapshot))

    def _delete_worker(self, paths, snapshot):
        """Delete the given paths, re-validating each one against the scan
        snapshot (size + mtime). Returns (removed, errors, changed).

        SAFETY: This worker re-checks the file's size and modification time
        against the snapshot taken during the scan. If the file has been
        modified since the scan, it is skipped to prevent accidental
        deletion of user data.
        """
        removed = 0
        errors = 0
        changed = 0
        for p in paths:
            if not os.path.exists(p):
                continue
            snap = snapshot.get(p)
            if snap is not None:
                try:
                    st = os.stat(p)
                    if (st.st_size, st.st_mtime_ns) != snap:
                        changed += 1
                        continue
                except OSError:
                    changed += 1
                    continue
            if _delete_path(p, to_recycle=self._recycle_enabled()):
                removed += 1
            else:
                errors += 1
        return removed, errors, changed

    def _recycle_enabled(self) -> bool:
        """True when the user opted for recycle-bin instead of delete."""
        return bool(getattr(self.host.settings,
                            "delete_to_recycle_bin", False))

    def _delete_done(self, removed, errors, changed) -> None:
        """Handle deletion completion."""
        self.host.set_busy(False)
        self.host.set_status(t("status.dupes_deleted", n=removed, e=errors))
        self.host.log(t("log.dupes_deleted", n=removed, e=errors))
        if changed:
            self.host.log(t("log.dupes_changed", n=changed))
        # Remove the deleted items from the tree.
        for i in range(self.tree.topLevelItemCount() - 1, -1, -1):
            parent = self.tree.topLevelItem(i)
            if parent is None:
                continue
            for j in range(parent.childCount() - 1, -1, -1):
                child = parent.child(j)
                if child is None:
                    continue
                p = item_data(child)
                if isinstance(p, str) and not os.path.exists(p):
                    parent.removeChild(child)
        app_info(self, "success", APP_NAME,
                 t("msg.dupes_deleted", n=removed))
