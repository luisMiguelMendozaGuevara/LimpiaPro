"""Page: uninstaller.

Lists installed programs from the registry, launches their uninstallers
safely (argument lists, never shell=True) and searches for leftover files
and registry keys afterwards. Leftover kinds are the stable English tags
from uninstall.find_leftovers ("folder"/"registry"), translated for
display via i18n."""

from tkinter import messagebox

import customtkinter as ctk

from .. import APP_NAME
from ..contracts import CleanerAppProtocol
from ..i18n import t
from ..uninstall import delete_registry_path, find_leftovers, get_installed_apps, launch_uninstaller
from ..utils import _delete_path, format_size
from .theme import MUTED, ORANGE, ORANGE_HOVER, RED, RED_HOVER, page_header
from .widgets import fill_tree, make_tree, readonly_toplevel, run_async, selected_one


class UninstallPage(ctk.CTkFrame):
    """Installed programs list with uninstall and leftover cleanup."""

    def __init__(self, master, app: CleanerAppProtocol):
        super().__init__(master, fg_color="transparent")
        self.app = app

        page_header(self, t("uninstall.title"), t("uninstall.subtitle"))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(10, 4))
        self.refresh_btn = ctk.CTkButton(
            bar, text=t("btn.refresh"), width=100, command=self.refresh
        )
        self.refresh_btn.pack(side="left")
        self.uninstall_btn = ctk.CTkButton(
            bar,
            text=t("btn.uninstall"),
            width=120,
            fg_color=ORANGE,
            hover_color=ORANGE_HOVER,
            command=self.uninstall_selected,
        )
        self.uninstall_btn.pack(side="left", padx=8)
        self.search_btn = ctk.CTkButton(
            bar, text=t("btn.find_leftovers"), width=120, command=self.search_leftovers
        )
        self.search_btn.pack(side="left", padx=8)
        self.del_btn = ctk.CTkButton(
            bar,
            text=t("btn.delete_leftovers"),
            width=130,
            fg_color=RED,
            hover_color=RED_HOVER,
            command=self.delete_leftovers,
        )
        self.del_btn.pack(side="left", padx=8)
        self.info = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.info.pack(side="right", padx=8)

        self.tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.tree_frame.pack(fill="both", expand=True)
        self.tree = make_tree(
            self.tree_frame,
            [
                ("#0", t("col.application"), 360),
                ("publisher", t("col.publisher"), 240),
                ("size", t("col.size"), 100, "e"),
            ],
        )

        self.apps = []
        self.leftovers = []
        self.refresh()

    def refresh(self):
        """Reload the installed programs list on a worker thread."""
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._load_worker, self._load_done, on_error=self._load_error)

    def _load_worker(self):
        """Enumerate the registry Uninstall keys off the UI thread."""
        return (get_installed_apps(),)

    def _load_error(self, exc):
        """Handle a failure of the app enumeration worker."""
        self.app.set_busy(False)
        self.info.configure(text=t("status.apps_load_error"))
        self.app.log(t("log.apps_load_error", exc=exc))

    def _load_done(self, apps):
        """Fill the tree with the installed applications."""
        self.app.set_busy(False)
        self.apps = apps
        specs = []
        for i, a in enumerate(apps):
            specs.append(
                (
                    str(i),
                    "",
                    a["name"],
                    (a["publisher"], format_size(a["size_kb"] * 1024) if a["size_kb"] else ""),
                    {},
                )
            )
        fill_tree(self.tree, specs)
        self.info.configure(text=t("uninstall.n_apps", n=len(apps)))
        self.app.log(t("log.apps_loaded", n=len(apps)))

    def on_busy(self, busy):
        """Toggle the page action buttons."""
        state = "disabled" if busy else "normal"
        for btn in (self.refresh_btn, self.uninstall_btn, self.search_btn, self.del_btn):
            btn.configure(state=state)

    def uninstall_selected(self):
        """Confirm and launch the selected program's uninstaller."""
        app = selected_one(self.tree, self.apps)
        if not app:
            return
        if not app["uninstall"]:
            messagebox.showwarning(APP_NAME, t("msg.no_uninstall_cmd"))
            return
        if not messagebox.askyesno(
            APP_NAME, t("msg.run_uninstaller", name=app["name"], cmd=app["uninstall"])
        ):
            return
        # No shell=True: the command is split, the executable is verified to
        # exist and launched with an argument list. Done on a worker because
        # split_command resolves against disk (System32/PATH).
        self.app.set_busy(True, mode="indeterminate")
        run_async(
            self.app,
            self._launch_worker,
            self._launch_done,
            (app,),
            on_error=lambda exc: self._launch_error(app, exc),
        )

    def _launch_worker(self, app):
        """Launch the uninstaller. Returns (name, ok, msg)."""
        return app["name"], *launch_uninstaller(app["uninstall"])

    def _launch_done(self, name, ok, msg):
        """Report whether the uninstaller process started."""
        self.app.set_busy(False)
        if ok:
            self.app.log(t("log.uninstaller_launched", name=name))
            self.app.set_status(t("status.uninstaller_launched", name=name))
        else:
            self.app.log(t("log.uninstaller_error", name=name, msg=msg))
            messagebox.showerror(APP_NAME, t("msg.uninstaller_error", msg=msg))

    def _launch_error(self, app, exc):
        """Handle an exception from the launch worker."""
        self.app.set_busy(False)
        messagebox.showerror(APP_NAME, t("msg.uninstaller_error", exc=exc))

    def search_leftovers(self):
        """Search disk and registry for leftovers of the selected app."""
        app = selected_one(self.tree, self.apps)
        if not app:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(
            self.app,
            self._leftover_worker,
            self._leftover_done,
            (app,),
            on_error=self._leftover_error,
        )

    def _leftover_worker(self, app):
        """Run the leftover search off the UI thread.
        Returns (name, results)."""
        results = find_leftovers(app["name"], app.get("location", ""))
        return app["name"], results

    def _leftover_error(self, exc):
        """Handle an exception from the leftover search."""
        self.app.set_busy(False)
        self.info.configure(text="")
        messagebox.showerror(APP_NAME, t("msg.leftover_error", exc=exc))

    def _leftover_done(self, name, results):
        """Show the found leftovers in a readonly Toplevel."""
        self.app.set_busy(False)
        self.leftovers = results
        self.info.configure(
            text=t("uninstall.leftover_count", name=name, n=len(results)) if results else ""
        )
        if not results:
            messagebox.showinfo(APP_NAME, t("msg.no_leftovers", name=name))
            return
        self.app.log(t("log.leftovers_found", name=name, n=len(results)))
        win, box = readonly_toplevel(
            self,
            t("title.leftovers"),
            "680x440",
            t("uninstall.leftovers_header", name=name, n=len(results)),
        )
        box.configure(state="normal")
        # kind is the stable English tag from find_leftovers; translated
        # for display here.
        box.insert("1.0", "\n".join(f"[{t('kind.' + kind)}] {p}" for kind, p in results))
        box.configure(state="disabled")

    def delete_leftovers(self):
        """Confirm and delete the previously found leftovers."""
        if not self.leftovers:
            messagebox.showinfo(APP_NAME, t("msg.search_first", btn=t("btn.find_leftovers")))
            return
        msg = t("msg.delete_generic_header") + "\n".join(f"  {p}" for _, p in self.leftovers[:20])
        if len(self.leftovers) > 20:
            msg += "\n" + t("msg.and_n_more", n=len(self.leftovers) - 20)
        msg += "\n\n" + t("ui.continue_q")
        if not messagebox.askyesno(APP_NAME, msg, icon="warning"):
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(
            self.app,
            self._delete_leftovers_worker,
            self._delete_leftovers_done,
            on_error=self._leftover_error,
        )

    def _delete_leftovers_worker(self):
        """Delete each leftover (registry keys recursively, folders/files
        otherwise). Returns (ok_count, error_count)."""
        ok = 0
        err = 0
        for kind, p in self.leftovers:
            deleted = delete_registry_path(p) if kind == "registry" else _delete_path(p)
            if deleted:
                ok += 1
            else:
                err += 1
        return ok, err

    def _delete_leftovers_done(self, ok, err):
        """Report the deletion result and clear the leftover state."""
        self.app.set_busy(False)
        self.leftovers = []
        self.info.configure(text="")
        self.app.log(t("log.leftovers_deleted", ok=ok, err=err))
        self.app.set_status(t("status.leftovers_deleted", ok=ok, err=err))
