"""Page: Startup manager (startup apps, scheduled tasks, processes).

Three sub-tabs in a CTkTabview, each one following the same pattern: a
worker gathers data off the UI thread via run_async, the done-callback
fills the Treeview in batches through fill_tree, and every entry point
respects the global app.busy guard. Startup app icons are extracted in
the worker (GDI+ is slow) and turned into PhotoImages on the UI thread."""

from tkinter import messagebox

import customtkinter as ctk

from .. import APP_NAME
from ..i18n import t
from ..processes import get_processes, is_protected, kill_process
from ..startup import get_disabled_startup, get_startup_apps, is_runonce_entry, set_startup
from ..tasks import get_scheduled_tasks, set_task_enabled
from ..winstyle import IconCache
from .theme import (
    GREEN,
    GREEN_HOVER,
    GREEN_TEXT,
    MUTED,
    ORANGE,
    ORANGE_HOVER,
    RED,
    RED_HOVER,
    page_header,
)
from .widgets import fill_tree, make_tree, run_async, selected_many, selected_one


class StartupPage(ctk.CTkFrame):
    """Startup apps, scheduled tasks and running processes manager."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        page_header(self, t("startup.title"), t("startup.subtitle"))

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=10)
        self.tabs.add(t("tab.startup_apps"))
        self.tabs.add(t("tab.tasks"))
        self.tabs.add(t("tab.processes"))
        self.tabs.set(t("tab.startup_apps"))

        self._build_startup_tab()
        self._build_tasks_tab()
        self._build_processes_tab()

    # ------------------------------------------------------------- startup apps

    def _build_startup_tab(self):
        """Build the startup apps tab: toolbar, icon cache and tree."""
        tab = self.tabs.tab(t("tab.startup_apps"))
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        self.startup_refresh_btn = ctk.CTkButton(toolbar, text=t("btn.refresh"), width=100,
                                                 command=self.refresh_startup)
        self.startup_refresh_btn.pack(side="left")
        self.startup_disable_btn = ctk.CTkButton(toolbar, text=t("btn.disable_selected"),
                                                 width=180,
                                                 fg_color=ORANGE, hover_color=ORANGE_HOVER,
                                                 command=self.disable_startup_selected)
        self.startup_disable_btn.pack(side="left", padx=8)
        ctk.CTkButton(toolbar, text=t("btn.reenable"), width=190,
                      command=self.show_disabled_startup).pack(side="left")

        self.icon_cache = IconCache(size=16)
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        self.startup_tree = make_tree(
            frame,
            [("#0", t("col.name"), 260), ("src", t("col.source"), 160),
             ("cmd", t("col.command"), 420)])
        self.startup_data = []

    def refresh_startup(self):
        """Load the startup apps list on a worker thread."""
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._startup_worker, self._startup_done,
                  on_error=lambda exc: self._generic_error(t("area.startup"), exc))

    def _startup_worker(self):
        """Gather startup entries and extract their icons as PNG bytes.

        Icon extraction happens off the UI thread (each extraction spins up
        GDI+ and touches disk); PhotoImages are built later on the UI
        thread. Returns (data, {command: png_bytes})."""
        data = get_startup_apps()
        icons = {}
        for e in data:
            cmd = e["command"] or ""
            img_bytes = self._icon_bytes(cmd)
            if img_bytes is not None:
                icons[cmd] = img_bytes
        return data, icons

    def _icon_bytes(self, command):
        """PNG bytes of the icon for a startup command (or None)."""
        from ..winstyle import get_file_icon_png
        return get_file_icon_png(command)

    def _startup_done(self, data, icons):
        """Fill the startup tree; icons are cached keyed by command line."""
        self.app.set_busy(False)
        self.startup_data = data
        # PhotoImages are created on the UI thread (tkinter requirement).
        cache = self.icon_cache
        for command, blob in icons.items():
            if command and command not in cache.cache:
                cache.cache[command] = cache._photo(blob)
        specs = []
        for i, e in enumerate(data):
            kw = {}
            img = cache.cache.get(e["command"] or "")
            if img is not None:
                kw["image"] = img
            specs.append((str(i), "", e["name"], (e["source"], e["command"]), kw))
        fill_tree(self.startup_tree, specs)
        self.app.log(t("log.startup_loaded", n=len(self.startup_data)))

    def disable_startup_selected(self):
        """Confirm and disable the selected startup app on a worker.
        
        RunOnce entries (P1-11) get a stronger warning because disabling
        them may prevent a one-time task from ever executing."""
        entry = selected_one(self.startup_tree, self.startup_data)
        if entry is None:
            return
        
        # Show stronger warning for RunOnce entries
        if is_runonce_entry(entry):
            msg = (
                f"⚠ ADVERTENCIA: Esta es una entrada de ejecución única (RunOnce).\n\n"
                f"Si la desactivas, puede que nunca se ejecute.\n\n"
                f"¿Estás seguro de que quieres desactivar '{entry['name']}'?"
            )
            if not messagebox.askyesno(APP_NAME, msg, icon="warning"):
                return
        else:
            if not messagebox.askyesno(
                    APP_NAME, t("msg.disable_startup", name=entry["name"])):
                return
        
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._disable_startup_worker,
                  self._disable_startup_done, (entry,))

    def _disable_startup_worker(self, entry):
        """Move a startup entry to its disabled counterpart.
        Returns (ok, msg, entry)."""
        ok, msg = set_startup(entry, False)
        return ok, msg, entry

    def _disable_startup_done(self, ok, msg, entry):
        """Report the disable result and refresh the list."""
        self.app.set_busy(False)
        if ok:
            self.app.log(t("log.startup_disabled", name=entry["name"]))
            self.app.set_status(t("status.startup_disabled", name=entry["name"]))
        else:
            self.app.set_status(t("status.startup_disable_error"))
            self.app.log(t("log.startup_disable_error",
                           name=entry["name"], msg=msg))
            messagebox.showerror(APP_NAME, t("msg.startup_disable_error", msg=msg))
        self.refresh_startup()

    def show_disabled_startup(self):
        """List disabled startup entries and offer re-enabling them."""
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._disabled_worker, self._disabled_done,
                  on_error=lambda exc: self._generic_error(t("area.disabled"), exc))

    def _disabled_worker(self):
        """Collect the disabled startup entries off the UI thread."""
        return get_disabled_startup(),

    def _disabled_done(self, disabled):
        """Open the re-enable dialog (Toplevel with a selection tree)."""
        self.app.set_busy(False)
        if not disabled:
            messagebox.showinfo(APP_NAME, t("msg.no_disabled"))
            return
        win = ctk.CTkToplevel(self)
        win.title(t("title.reattach"))
        win.geometry("640x420")
        ctk.CTkLabel(win, text=t("startup.reattach_label"),
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=14, pady=(10, 4))
        frame = ctk.CTkFrame(win, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        tree = make_tree(frame, [("#0", t("col.name"), 240),
                                 ("cmd", t("col.cmd_file"), 360)])
        specs = [(str(i), "", e["name"], (e["command"] or e.get("filename", "")), {})
                 for i, e in enumerate(disabled)]
        fill_tree(tree, specs)

        def _re():
            sel = selected_many(tree, disabled)
            if not sel:
                return
            self.app.set_busy(True, mode="indeterminate")
            run_async(self.app, self._reenable_worker,
                      self._reenable_done, (sel, win))

        ctk.CTkButton(win, text=t("btn.reenable_selected"), width=180,
                      fg_color=GREEN, hover_color=GREEN_HOVER, command=_re).pack(padx=14, pady=8)

    def _reenable_worker(self, entries, win):
        """Re-enable the selected entries; the dialog closes afterwards.
        Returns (results, win)."""
        results = []
        for entry in entries:
            ok, msg = set_startup(entry, True)
            results.append((entry["name"], ok, msg))
        return results, win

    def _reenable_done(self, results, win):
        """Log each re-enable result, close the dialog and refresh."""
        self.app.set_busy(False)
        for name, ok, msg in results:
            if ok:
                self.app.log(t("log.startup_enabled", name=name))
            else:
                self.app.log(t("log.startup_enable_error", name=name, msg=msg))
        win.destroy()
        self.refresh_startup()

    def on_busy(self, busy):
        """Toggle the startup-tab action buttons."""
        state = "disabled" if busy else "normal"
        for btn in (self.startup_refresh_btn, self.startup_disable_btn):
            btn.configure(state=state)

    # ------------------------------------------------------------- scheduled tasks

    def _build_tasks_tab(self):
        """Build the scheduled tasks tab: toolbar and tasks tree."""
        tab = self.tabs.tab(t("tab.tasks"))
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        self.tasks_refresh_btn = ctk.CTkButton(toolbar, text=t("btn.refresh"), width=100,
                                               command=self.refresh_tasks)
        self.tasks_refresh_btn.pack(side="left")
        self.tasks_disable_btn = ctk.CTkButton(toolbar, text=t("btn.disable"), width=110,
                                               fg_color=ORANGE, hover_color=ORANGE_HOVER,
                                               command=lambda: self._toggle_task(False))
        self.tasks_disable_btn.pack(side="left", padx=8)
        self.tasks_enable_btn = ctk.CTkButton(toolbar, text=t("btn.enable"), width=100,
                                              fg_color=GREEN, hover_color=GREEN_HOVER,
                                              command=lambda: self._toggle_task(True))
        self.tasks_enable_btn.pack(side="left")
        self.tasks_info = ctk.CTkLabel(toolbar, text="", text_color=MUTED)
        self.tasks_info.pack(side="right", padx=8)

        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        self.tasks_tree = make_tree(
            frame,
            [("#0", t("col.task"), 300), ("status", t("col.status"), 90, "center"),
             ("sched", t("col.schedule"), 130, "center"),
             ("next", t("col.next_run"), 180)])
        self.tasks_data = []

    def refresh_tasks(self):
        """Reload the scheduled tasks list (one batched schtasks query)."""
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._refresh_tasks_worker, self._refresh_tasks_done,
                  on_error=lambda exc: self._generic_error(t("area.tasks"), exc))

    def _refresh_tasks_worker(self):
        """Query schtasks off the UI thread."""
        return (get_scheduled_tasks(),)

    def _refresh_tasks_done(self, tasks):
        """Fill the tasks tree with enabled/disabled row tagging."""
        self.app.set_busy(False)
        self.tasks_data = tasks
        enabled = 0
        disabled = 0
        specs = []
        for i, task in enumerate(tasks):
            state = task.get("scheduled") or task.get("status", "")
            is_disabled = ("disabled" in state.lower())
            if is_disabled:
                disabled += 1
            else:
                enabled += 1
            tag = "disabled" if is_disabled else "enabled"
            specs.append((str(i), "", task["name"],
                          (state, task.get("status", ""), task.get("next", "")),
                          {"tags": (tag,)}))
        self.tasks_tree.tag_configure("disabled", foreground=ORANGE)
        self.tasks_tree.tag_configure("enabled", foreground=GREEN_TEXT)
        fill_tree(self.tasks_tree, specs)
        self.tasks_info.configure(
            text=t("startup.tasks_count", n=enabled, m=disabled))
        self.app.log(t("log.tasks_loaded", n=len(tasks)))

    def _toggle_task(self, enable):
        """Confirm and enable/disable the selected scheduled task."""
        task = selected_one(self.tasks_tree, self.tasks_data)
        if task is None:
            return
        key = "msg.task_enable_q" if enable else "msg.task_disable_q"
        if not messagebox.askyesno(APP_NAME, t(key, name=task["name"])):
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._toggle_task_worker,
                  self._toggle_task_done, (task["name"], enable))

    def _toggle_task_worker(self, name, enable):
        """Flip one task through schtasks. Returns (ok, msg, name, enable)."""
        ok, msg = set_task_enabled(name, enable)
        return ok, msg, name, enable

    def _toggle_task_done(self, ok, msg, name, enable):
        """Report the toggle result and refresh the task list."""
        self.app.set_busy(False)
        key = "status.task_enabled" if enable else "status.task_disabled"
        logkey = "log.task_enabled" if enable else "log.task_disabled"
        if ok:
            self.app.log(t(logkey, name=name))
            self.app.set_status(t(key, name=name))
        else:
            self.app.set_status(t("status.task_error"))
            self.app.log(t("log.task_error", name=name, msg=msg))
            messagebox.showerror(APP_NAME, t("msg.task_error", msg=msg))
        self.refresh_tasks()

    # ------------------------------------------------------------- processes

    def _build_processes_tab(self):
        """Build the running processes tab: toolbar, search box and tree."""
        tab = self.tabs.tab(t("tab.processes"))
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        self.proc_refresh_btn = ctk.CTkButton(toolbar, text=t("btn.refresh"), width=100,
                                              command=self.refresh_processes)
        self.proc_refresh_btn.pack(side="left")
        self.kill_btn = ctk.CTkButton(toolbar, text=t("btn.end_process"), width=140,
                                      fg_color=RED, hover_color=RED_HOVER,
                                      command=self.kill_selected)
        self.kill_btn.pack(side="left", padx=8)
        self.proc_search_var = ctk.StringVar()
        ctk.CTkEntry(toolbar, textvariable=self.proc_search_var,
                     placeholder_text=t("startup.search_placeholder"),
                     width=220).pack(side="right", padx=6)
        ctk.CTkButton(toolbar, text=t("btn.filter"), width=70,
                      command=self.refresh_processes).pack(side="right")

        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        self.proc_tree = make_tree(
            frame,
            [("#0", t("col.process"), 260), ("pid", "PID", 70, "center"),
             ("session", t("col.session"), 80, "center"),
             ("mem", t("col.memory"), 90, "e"),
             ("user", t("col.user"), 160)])
        self.proc_data = []

    def refresh_processes(self):
        """Reload the process list, applying the search filter."""
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._refresh_processes_worker, self._refresh_processes_done,
                  on_error=lambda exc: self._generic_error(t("area.processes"), exc))

    def _refresh_processes_worker(self):
        """Query tasklist off the UI thread."""
        return (get_processes(),)

    def _refresh_processes_done(self, procs):
        """Fill the process tree (iids are PIDs) applying the name filter."""
        self.app.set_busy(False)
        self.proc_data = procs
        search = self.proc_search_var.get().strip().lower()
        specs = []
        count = 0
        for p in procs:
            if search and search not in p["name"].lower():
                continue
            count += 1
            specs.append((str(p["pid"]), "", p["name"],
                          (p["pid"], p["session"], p["mem"], p["user"]), {}))
        fill_tree(self.proc_tree, specs)
        self.app.log(t("log.processes_shown", n=count))

    def _generic_error(self, area, exc):
        """Shared error handler for failed list loads: reset busy, log and
        show a dialog."""
        self.app.set_busy(False)
        self.app.set_status(t("status.load_error", area=area))
        self.app.log(t("log.load_error", area=area, exc=exc))
        messagebox.showerror(APP_NAME, t("msg.load_error", area=area, exc=exc))

    def kill_selected(self):
        """Confirm and force-end the selected process."""
        sel = self.proc_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, t("msg.select_process"))
            return
        pid = sel[0]
        name = self.proc_tree.item(pid, "text")
        if is_protected(name):
            messagebox.showinfo(APP_NAME, t("msg.process_protected", name=name))
            return
        if not messagebox.askyesno(
                APP_NAME, t("msg.kill_process", name=name, pid=pid)):
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._kill_worker, self._kill_done, (pid, name))

    def _kill_worker(self, pid, name):
        """Force-end one process via taskkill. Returns (ok, msg, name)."""
        ok, msg = kill_process(pid, name=name)
        return ok, msg, name

    def _kill_done(self, ok, msg, name):
        """Report the kill result and refresh the process list."""
        self.app.set_busy(False)
        if ok:
            self.app.log(t("log.process_killed", name=name))
            self.app.set_status(t("status.process_killed", name=name))
        else:
            self.app.set_status(t("status.process_error"))
            self.app.log(t("log.process_error", name=name, msg=msg))
            messagebox.showerror(APP_NAME, t("msg.process_error", msg=msg))
        self.refresh_processes()
