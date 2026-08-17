"""Page: duplicate files finder.

Drives DuplicateScanner on a worker thread: the user picks a folder and a
minimum size, results are shown as tree groups (one "original" plus its
copies) and the selected copies get deleted after confirmation. Each item
carries an explicit stable iid; _item_path maps the file rows back to their
paths so deletion never relies on the displayed tree text."""

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import APP_NAME
from ..duplicates import DuplicateScanner
from ..i18n import t
from ..utils import _delete_path, _safe_size, format_size
from .theme import GREEN, GREEN_HOVER, MUTED, RED, RED_HOVER, page_header
from .widgets import fill_tree, make_tree, run_async


class DuplicatePage(ctk.CTkFrame):
    """Duplicate file scanner page: folder picker, scan and delete."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        page_header(self, t("dupes.title"), t("dupes.subtitle"))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=10)
        self.folder_path = ctk.StringVar(value="")
        ctk.CTkButton(bar, text=t("btn.choose_folder"), width=130,
                      command=self.choose_folder).pack(side="left")
        ctk.CTkEntry(bar, textvariable=self.folder_path,
                     placeholder_text=t("dupes.path_placeholder"),
                     state="readonly").pack(side="left", fill="x", expand=True, padx=8)
        self.min_size = ctk.StringVar(value="2 MB")
        ctk.CTkLabel(bar, text=t("dupes.min_size")).pack(side="left")
        ctk.CTkOptionMenu(bar, values=["1 MB", "2 MB", "5 MB", "10 MB", "50 MB"],
                          variable=self.min_size, width=90).pack(side="left", padx=6)
        self.scan_btn = ctk.CTkButton(bar, text=t("btn.find_dupes"), width=140,
                                      fg_color=GREEN,
                                      hover_color=GREEN_HOVER, command=self.start_scan)
        self.scan_btn.pack(side="left", padx=6)

        self.info = ctk.CTkLabel(self, text="", text_color=MUTED)
        self.info.pack(anchor="w", padx=16)

        # iid -> file path for the duplicate copy rows (group headers and
        # the "original" placeholder row have no path).
        self._item_path = {}

        self.tree_frame = ctk.CTkFrame(self, fg_color=("gray92", "#1c1c1e"))
        self.tree_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self.tree = make_tree(
            self.tree_frame,
            [("#0", t("col.file_group"), 560), ("dup", t("col.copies"), 70, "center"),
             ("size", t("col.size"), 90, "e")])

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(4, 10))
        sel_help = ctk.CTkLabel(
            bottom, text=t("dupes.help", btn=t("btn.delete_selected")),
            font=ctk.CTkFont(size=11), text_color=MUTED)
        sel_help.pack(side="left")
        self.summary = ctk.CTkLabel(bottom, text="",
                                    font=ctk.CTkFont(size=12, weight="bold"))
        self.summary.pack(side="left", padx=12)
        self.delete_btn = ctk.CTkButton(bottom, text=t("btn.delete_selected"), width=180,
                                        fg_color=RED, hover_color=RED_HOVER,
                                        command=self.delete_selected)
        self.delete_btn.pack(side="right")

    def on_busy(self, busy):
        """Toggle the scan/delete buttons."""
        state = "disabled" if busy else "normal"
        self.scan_btn.configure(state=state)
        self.delete_btn.configure(state=state)

    def choose_folder(self):
        """Open the folder picker and store the chosen path."""
        path = filedialog.askdirectory(title=t("dialog.pick_folder"))
        if path:
            self.folder_path.set(path)

    def _tree_path(self, item_id):
        """File path of a tree item, or None.

        Looks the iid up in _item_path; rows without an entry (group
        headers, the "(original, kept)" placeholder) return None. The tree
        text is never parsed, so paths containing '(' or ')' are found
        reliably."""
        return self._item_path.get(item_id)

    def start_scan(self):
        """Validate input and launch the scan on a worker thread."""
        if self.app.busy:
            return
        folder = self.folder_path.get()
        if not folder:
            messagebox.showinfo(APP_NAME, t("msg.dupes_no_folder"))
            return
        min_mb = int(self.min_size.get().split()[0])
        self.app.set_status(t("status.dupes_scanning", folder=folder))
        self.app.set_busy(True, mode="indeterminate")
        self.app.scanner = DuplicateScanner(folder, min_mb)
        self.tree.delete(*self.tree.get_children())
        self._item_path = {}
        self.summary.configure(text=t("label.scanning"))
        self.info.configure(text="")
        self._scan_folder = folder
        run_async(self.app, self._scan_worker, self._done, (folder,),
                  on_error=self._scan_error)

    def _scan_worker(self, folder):
        """Run the scanner phases (size -> prehash -> full hash).
        Returns (groups, None); the second slot is kept for symmetry with
        _done's error branch."""
        return self.app.scanner.scan(), None

    def _scan_error(self, exc):
        """Handle an exception raised by the scan worker."""
        self.app.set_busy(False)
        self.summary.configure(text="")
        self.app.set_status(t("status.dupes_failed"))
        self.app.log(t("log.dupes_error", exc=exc))
        messagebox.showerror(APP_NAME, t("msg.error_simple", exc=exc))

    def _done(self, groups, error):
        """Fill the tree with the resulting duplicate groups."""
        self.app.set_busy(False)
        if error:
            self.summary.configure(text="")
            self.app.set_status(t("status.dupes_failed"))
            self.app.log(t("log.dupes_error", exc=error))
            messagebox.showerror(APP_NAME, t("msg.error_simple", exc=error))
            return
        self.tree.delete(*self.tree.get_children())
        if not groups:
            self.app.set_status(t("status.dupes_none"))
            self.summary.configure(text=t("dupes.none_found"))
            self.info.configure(text="")
            return
        dup_count = sum(len(g) - 1 for g in groups)
        wasted = sum(_safe_size(g[0]) * (len(g) - 1) for g in groups)
        self.summary.configure(
            text=t("dupes.summary", n=len(groups), size=format_size(wasted)))
        info = t("dupes.results_of", folder=self.folder_path.get())
        skipped = getattr(self.app.scanner, "skipped", 0)
        if skipped:
            info += " " + t("dupes.unreadable", n=skipped)
        self.info.configure(text=info)
        specs = []
        iid_n = 0
        for gi, group in enumerate(groups):
            gid = f"g{gi}"
            head = t("dupes.group_head",
                     name=os.path.basename(group[0]),
                     size=format_size(_safe_size(group[0])))
            specs.append((gid, "", head, (str(len(group)), ""), {"open": False}))
            specs.append(("", gid, t("dupes.original"), ("", ""), {}))
            for dup in group[1:]:
                pid = f"p{iid_n}"
                iid_n += 1
                self._item_path[pid] = dup
                specs.append((pid, gid, dup, ("", ""), {}))
        fill_tree(self.tree, specs)
        self.app.set_status(t("status.dupes_done", n=len(groups)))
        self.app.log(t("log.dupes_done", folder=self.folder_path.get(),
                       n=len(groups), m=dup_count, size=format_size(wasted)))

    def delete_selected(self):
        """Confirm and delete the selected duplicate copies on a worker."""
        selected = [self._tree_path(i) for i in self.tree.selection()]
        paths = [p for p in selected if p]
        if not paths:
            messagebox.showinfo(APP_NAME, t("msg.dupes_select"))
            return
        msg = t("msg.delete_files_header") + "\n".join(paths[:15])
        if len(paths) > 15:
            msg += "\n" + t("msg.and_n_more", n=len(paths) - 15)
        msg += ("\n\n" + t("msg.space_to_free",
                           size=format_size(sum(_safe_size(p) for p in paths)))
                + "\n\n" + t("ui.continue_q"))
        if not messagebox.askyesno(APP_NAME, msg, icon="warning"):
            return
        self.app.set_busy(True, mode="indeterminate")
        # Frozen copy of the scan snapshot: re-validate each file against
        # it before deleting (a file that changed since the scan must not
        # be destroyed just because it shares a name/group).
        snapshot = dict(getattr(self.app.scanner, "snapshot", {}))
        run_async(self.app, self._delete_worker, self._delete_done,
                  (paths, snapshot))

    def _delete_worker(self, paths, snapshot):
        """Delete the given paths, re-validating each one against the scan
        snapshot (size + mtime) so files modified after the scan are left
        alone. Returns (removed, errors, changed)."""
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
            if _delete_path(p):
                removed += 1
            else:
                errors += 1
        return removed, errors, changed

    def _delete_done(self, removed, errors, changed):
        """Report the result and prune the deleted rows from the tree."""
        self.app.set_busy(False)
        self.app.set_status(t("status.dupes_deleted", n=removed, e=errors))
        self.app.log(t("log.dupes_deleted", n=removed, e=errors))
        if changed:
            self.app.log(t("log.dupes_changed", n=changed))
        # Remove the deleted items from the tree.
        for item_id in self.tree.get_children():
            for child in self.tree.get_children(item_id):
                p = self._tree_path(child)
                if p and not os.path.exists(p):
                    self.tree.delete(child)
        messagebox.showinfo(APP_NAME, t("msg.dupes_deleted", n=removed))
