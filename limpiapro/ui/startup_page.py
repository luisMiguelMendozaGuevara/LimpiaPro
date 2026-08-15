"""Pagina: Inicio (apps de inicio, tareas programadas, procesos)."""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from .. import APP_NAME
from ..processes import get_processes, kill_process
from ..startup import (get_disabled_startup, get_startup_apps, set_startup)
from ..tasks import get_scheduled_tasks, set_task_enabled
from ..winstyle import IconCache, fluent_font
from .widgets import make_tree, run_async, selected_many, selected_one


class StartupPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(self, text="Administrador de inicio",
                     font=fluent_font(20, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(self, text="Apps que arrancan con Windows, tareas programadas y procesos activos.",
                     font=fluent_font(12), text_color=("gray40", "gray60")).pack(anchor="w", padx=16)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=10)
        self.tabs.add("Apps de inicio")
        self.tabs.add("Tareas programadas")
        self.tabs.add("Procesos activos")
        self.tabs.set("Apps de inicio")

        self._build_startup_tab()
        self._build_tasks_tab()
        self._build_processes_tab()

    # ------------------------------------------------------------- apps de inicio

    def _build_startup_tab(self):
        tab = self.tabs.tab("Apps de inicio")
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkButton(toolbar, text="Refrescar", width=100, command=self.refresh_startup).pack(side="left")
        self.startup_disable_btn = ctk.CTkButton(toolbar, text="Desactivar seleccionada", width=180,
                                                 fg_color="#e65100", hover_color="#ef6c00",
                                                 command=self.disable_startup_selected)
        self.startup_disable_btn.pack(side="left", padx=8)
        ctk.CTkButton(toolbar, text="Reactivar desactivadas...", width=190,
                      command=self.show_disabled_startup).pack(side="left")

        self.icon_cache = IconCache(size=16)
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        self.startup_tree = make_tree(
            frame,
            [("#0", "Nombre", 260), ("src", "Origen", 160),
             ("cmd", "Comando", 420)])
        self.app._restyle_tree()
        self.startup_data = []

    def refresh_startup(self):
        self.startup_data = get_startup_apps()
        self._fill_tree(self.startup_tree, self.startup_data,
                        lambda e: (e["name"], e["source"], e["command"]),
                        icon_key="command")
        self.app.log(f"Apps de inicio: {len(self.startup_data)} encontradas.")

    def disable_startup_selected(self):
        entry = selected_one(self.startup_tree, self.startup_data)
        if entry is None:
            return
        if not messagebox.askyesno(
                APP_NAME,
                f"Desactivar el inicio de:\n\n  {entry['name']}\n\n"
                f"Se movera a la lista de desactivadas y podras reactivarla despues."):
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._disable_startup_worker,
                  self._disable_startup_done, (entry,))

    def _disable_startup_worker(self, entry):
        return set_startup(entry, False)

    def _disable_startup_done(self, ok, msg, entry):
        self.app.set_busy(False)
        if ok:
            self.app.log(f"Desactivada app de inicio: {entry['name']}")
            self.app.set_status(f"App de inicio desactivada: {entry['name']}")
        else:
            self.app.set_status("Error al desactivar")
            self.app.log(f"Error desactivando {entry['name']}: {msg}")
            messagebox.showerror(APP_NAME, f"No se pudo desactivar:\n{msg}")
        self.refresh_startup()

    def show_disabled_startup(self):
        disabled = get_disabled_startup()
        if not disabled:
            messagebox.showinfo(APP_NAME, "No hay aplicaciones de inicio desactivadas.")
            return
        win = ctk.CTkToplevel(self)
        win.title("Reactivar aplicaciones de inicio")
        win.geometry("640x420")
        ctk.CTkLabel(win, text="Selecciona las aplicaciones a reactivar",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=14, pady=(10, 4))
        frame = ctk.CTkFrame(win, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        tree = make_tree(frame, [("#0", "Nombre", 240), ("cmd", "Comando / archivo", 360)])
        for i, e in enumerate(disabled):
            tree.insert("", "end", iid=str(i), text=e["name"],
                        values=(e["command"] or e.get("filename", "")))

        def _re():
            sel = selected_many(tree, disabled)
            if not sel:
                return
            self.app.set_busy(True, mode="indeterminate")
            run_async(self.app, self._reenable_worker,
                      self._reenable_done, (sel, win))

        ctk.CTkButton(win, text="Reactivar seleccionadas", width=180, fg_color="#2e7d32",
                      hover_color="#388e3c", command=_re).pack(padx=14, pady=8)

    def _reenable_worker(self, entries, win):
        results = []
        for entry in entries:
            ok, msg = set_startup(entry, True)
            results.append((entry["name"], ok, msg))
        return results, win

    def _reenable_done(self, results, win):
        self.app.set_busy(False)
        for name, ok, msg in results:
            if ok:
                self.app.log(f"Reactivada app de inicio: {name}")
            else:
                self.app.log(f"Error reactivando {name}: {msg}")
        win.destroy()
        self.refresh_startup()

    # ------------------------------------------------------------- tareas programadas

    def _build_tasks_tab(self):
        tab = self.tabs.tab("Tareas programadas")
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkButton(toolbar, text="Refrescar", width=100, command=self.refresh_tasks).pack(side="left")
        self.tasks_disable_btn = ctk.CTkButton(toolbar, text="Desactivar", width=110,
                                               fg_color="#e65100", hover_color="#ef6c00",
                                               command=lambda: self._toggle_task(False))
        self.tasks_disable_btn.pack(side="left", padx=8)
        ctk.CTkButton(toolbar, text="Activar", width=100, fg_color="#2e7d32",
                      hover_color="#388e3c", command=lambda: self._toggle_task(True)).pack(side="left")
        self.tasks_info = ctk.CTkLabel(toolbar, text="", text_color=("gray40", "gray60"))
        self.tasks_info.pack(side="right", padx=8)

        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        self.tasks_tree = make_tree(
            frame,
            [("#0", "Tarea", 300), ("status", "Estado", 90, "center"),
             ("sched", "Planificacion", 130, "center"),
             ("next", "Proxima ejecucion", 180)])
        self.app._restyle_tree()
        self.tasks_data = []

    def refresh_tasks(self):
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._refresh_tasks_worker, self._refresh_tasks_done)

    def _refresh_tasks_worker(self):
        return (get_scheduled_tasks(),)

    def _refresh_tasks_done(self, tasks):
        self.app.set_busy(False)
        self.tasks_data = tasks
        for item in self.tasks_tree.get_children():
            self.tasks_tree.delete(item)
        enabled = 0
        disabled = 0
        for i, t in enumerate(tasks):
            state = t.get("scheduled") or t.get("status", "")
            is_disabled = ("disabled" in state.lower())
            if is_disabled:
                disabled += 1
            else:
                enabled += 1
            tag = "disabled" if is_disabled else "enabled"
            self.tasks_tree.insert("", "end", iid=str(i), text=t["name"],
                                   values=(state, t.get("status", ""), t.get("next", "")),
                                   tags=(tag,))
        self.tasks_tree.tag_configure("disabled", foreground="#e65100")
        self.tasks_tree.tag_configure("enabled", foreground="#2e9e5b")
        self.tasks_info.configure(text=f"{enabled} activas · {disabled} desactivadas")
        self.app.log(f"Tareas programadas: {len(tasks)} cargadas.")

    def _toggle_task(self, enable):
        task = selected_one(self.tasks_tree, self.tasks_data)
        if task is None:
            return
        action = "ACTIVAR" if enable else "DESACTIVAR"
        if not messagebox.askyesno(APP_NAME, f"{action} la tarea:\n\n  {task['name']} ?"):
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._toggle_task_worker,
                  self._toggle_task_done, (task["name"], enable))

    def _toggle_task_worker(self, name, enable):
        return set_task_enabled(name, enable)

    def _toggle_task_done(self, ok, msg, name, enable):
        self.app.set_busy(False)
        verb = "activada" if enable else "desactivada"
        if ok:
            self.app.log(f"Tarea {verb}: {name}")
            self.app.set_status(f"Tarea {verb}: {name}")
        else:
            self.app.set_status("Error al modificar tarea")
            self.app.log(f"Error en tarea {name}: {msg}")
            messagebox.showerror(APP_NAME, f"No se pudo modificar:\n{msg}\n\n(requiere administrador)")
        self.refresh_tasks()

    # ------------------------------------------------------------- procesos activos

    def _build_processes_tab(self):
        tab = self.tabs.tab("Procesos activos")
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        ctk.CTkButton(toolbar, text="Refrescar", width=100, command=self.refresh_processes).pack(side="left")
        self.kill_btn = ctk.CTkButton(toolbar, text="Terminar proceso", width=140,
                                      fg_color="#c62828", hover_color="#d32f2f",
                                      command=self.kill_selected)
        self.kill_btn.pack(side="left", padx=8)
        self.proc_search_var = ctk.StringVar()
        ctk.CTkEntry(toolbar, textvariable=self.proc_search_var, placeholder_text="Buscar proceso...",
                     width=220).pack(side="right", padx=6)
        ctk.CTkButton(toolbar, text="Filtrar", width=70, command=self.refresh_processes).pack(side="right")

        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        self.proc_tree = make_tree(
            frame,
            [("#0", "Proceso", 260), ("pid", "PID", 70, "center"),
             ("session", "Sesion", 80, "center"), ("mem", "Memoria", 90, "e"),
             ("user", "Usuario", 160)])
        self.app._restyle_tree()
        self.proc_data = []

    def refresh_processes(self):
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._refresh_processes_worker, self._refresh_processes_done)

    def _refresh_processes_worker(self):
        return (get_processes(),)

    def _refresh_processes_done(self, procs):
        self.app.set_busy(False)
        self.proc_data = procs
        search = self.proc_search_var.get().strip().lower()
        for item in self.proc_tree.get_children():
            self.proc_tree.delete(item)
        count = 0
        for p in procs:
            if search and search not in p["name"].lower():
                continue
            count += 1
            self.proc_tree.insert("", "end", iid=p["pid"],
                                  text=p["name"],
                                  values=(p["pid"], p["session"], p["mem"], p["user"]))
        self.app.log(f"Procesos: {count} mostrados.")

    def kill_selected(self):
        sel = self.proc_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "Selecciona un proceso en la lista.")
            return
        pid = sel[0]
        name = self.proc_tree.item(pid, "text")
        if not messagebox.askyesno(APP_NAME,
                                   f"Terminar el proceso:\n\n  {name} (PID {pid}) ?\n\n"
                                   "Se cerrara de forma forzosa y se perderan cambios sin guardar."):
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._kill_worker, self._kill_done, (pid, name))

    def _kill_worker(self, pid, name):
        return kill_process(pid)

    def _kill_done(self, ok, msg, name):
        self.app.set_busy(False)
        if ok:
            self.app.log(f"Proceso terminado: {name}")
            self.app.set_status(f"Proceso terminado: {name}")
        else:
            self.app.set_status("Error al terminar proceso")
            self.app.log(f"Error terminando {name}: {msg}")
            messagebox.showerror(APP_NAME, f"No se pudo terminar:\n{msg}")
        self.refresh_processes()

    def _fill_tree(self, tree, data, row_fn, icon_key=None):
        for item in tree.get_children():
            tree.delete(item)
        for i, entry in enumerate(data):
            name, src, cmd = row_fn(entry)
            kw = {}
            if icon_key is not None:
                img = self.icon_cache.get(entry.get(icon_key) or "")
                if img is not None:
                    kw["image"] = img
            tree.insert("", "end", iid=str(i), text=name, values=(src, cmd), **kw)
