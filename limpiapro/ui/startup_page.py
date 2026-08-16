"""Pagina: Inicio (apps de inicio, tareas programadas, procesos)."""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from .. import APP_NAME
from ..processes import get_processes, kill_process
from ..startup import (get_disabled_startup, get_startup_apps, set_startup)
from ..tasks import get_scheduled_tasks, set_task_enabled
from ..winstyle import IconCache
from .theme import (GREEN, GREEN_HOVER, GREEN_TEXT, MUTED, ORANGE,
                    ORANGE_HOVER, RED, RED_HOVER, page_header)
from .widgets import fill_tree, make_tree, run_async, selected_many, selected_one


class StartupPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        page_header(self, "Administrador de inicio",
                    "Apps que arrancan con Windows, tareas programadas y procesos activos.")

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
        self.startup_refresh_btn = ctk.CTkButton(toolbar, text="Refrescar", width=100,
                                                 command=self.refresh_startup)
        self.startup_refresh_btn.pack(side="left")
        self.startup_disable_btn = ctk.CTkButton(toolbar, text="Desactivar seleccionada", width=180,
                                                 fg_color=ORANGE, hover_color=ORANGE_HOVER,
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
        self.startup_data = []

    def refresh_startup(self):
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._startup_worker, self._startup_done,
                  on_error=lambda exc: self._generic_error("inicio", exc))

    def _startup_worker(self):
        data = get_startup_apps()
        # Extraccion de iconos fuera del hilo de UI: devolvemos {ruta: png_bytes}.
        icons = {}
        for e in data:
            cmd = e["command"] or ""
            img_bytes = self._icon_bytes(cmd)
            if img_bytes is not None:
                icons[cmd] = img_bytes
        return data, icons

    def _icon_bytes(self, command):
        from ..winstyle import get_file_icon_png
        return get_file_icon_png(command)

    def _startup_done(self, data, icons):
        self.app.set_busy(False)
        self.startup_data = data
        # Los PhotoImage se construyen en el hilo de UI (tkinter).
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
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._disabled_worker, self._disabled_done,
                  on_error=lambda exc: self._generic_error("desactivadas", exc))

    def _disabled_worker(self):
        return get_disabled_startup(),

    def _disabled_done(self, disabled):
        self.app.set_busy(False)
        if not disabled:
            messagebox.showinfo(APP_NAME,
                                "No hay aplicaciones de inicio desactivadas.")
            return
        win = ctk.CTkToplevel(self)
        win.title("Reactivar aplicaciones de inicio")
        win.geometry("640x420")
        ctk.CTkLabel(win, text="Selecciona las aplicaciones a reactivar",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=14, pady=(10, 4))
        frame = ctk.CTkFrame(win, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        tree = make_tree(frame, [("#0", "Nombre", 240), ("cmd", "Comando / archivo", 360)])
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

        ctk.CTkButton(win, text="Reactivar seleccionadas", width=180, fg_color=GREEN, hover_color=GREEN_HOVER, command=_re).pack(padx=14, pady=8)

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

    def on_busy(self, busy):
        state = "disabled" if busy else "normal"
        for btn in (self.startup_refresh_btn, self.startup_disable_btn):
            btn.configure(state=state)

    def _build_tasks_tab(self):
        tab = self.tabs.tab("Tareas programadas")
        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(8, 4))
        self.tasks_refresh_btn = ctk.CTkButton(toolbar, text="Refrescar", width=100,
                                               command=self.refresh_tasks)
        self.tasks_refresh_btn.pack(side="left")
        self.tasks_disable_btn = ctk.CTkButton(toolbar, text="Desactivar", width=110,
                                               fg_color=ORANGE, hover_color=ORANGE_HOVER,
                                               command=lambda: self._toggle_task(False))
        self.tasks_disable_btn.pack(side="left", padx=8)
        self.tasks_enable_btn = ctk.CTkButton(toolbar, text="Activar", width=100, fg_color=GREEN, hover_color=GREEN_HOVER,
                                              command=lambda: self._toggle_task(True))
        self.tasks_enable_btn.pack(side="left")
        self.tasks_info = ctk.CTkLabel(toolbar, text="", text_color=MUTED)
        self.tasks_info.pack(side="right", padx=8)

        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(fill="both", expand=True)
        self.tasks_tree = make_tree(
            frame,
            [("#0", "Tarea", 300), ("status", "Estado", 90, "center"),
             ("sched", "Planificacion", 130, "center"),
             ("next", "Proxima ejecucion", 180)])
        self.tasks_data = []

    def refresh_tasks(self):
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._refresh_tasks_worker, self._refresh_tasks_done,
                  on_error=lambda exc: self._generic_error("tareas", exc))

    def _refresh_tasks_worker(self):
        return (get_scheduled_tasks(),)

    def _refresh_tasks_done(self, tasks):
        self.app.set_busy(False)
        self.tasks_data = tasks
        enabled = 0
        disabled = 0
        specs = []
        for i, t in enumerate(tasks):
            state = t.get("scheduled") or t.get("status", "")
            is_disabled = ("disabled" in state.lower())
            if is_disabled:
                disabled += 1
            else:
                enabled += 1
            tag = "disabled" if is_disabled else "enabled"
            specs.append((str(i), "", t["name"],
                          (state, t.get("status", ""), t.get("next", "")),
                          {"tags": (tag,)}))
        self.tasks_tree.tag_configure("disabled", foreground=ORANGE)
        self.tasks_tree.tag_configure("enabled", foreground=GREEN_TEXT)
        fill_tree(self.tasks_tree, specs)
        self.tasks_info.configure(text=f"{enabled} activas - {disabled} desactivadas")
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
        self.proc_refresh_btn = ctk.CTkButton(toolbar, text="Refrescar", width=100,
                                              command=self.refresh_processes)
        self.proc_refresh_btn.pack(side="left")
        self.kill_btn = ctk.CTkButton(toolbar, text="Terminar proceso", width=140,
                                      fg_color=RED, hover_color=RED_HOVER,
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
        self.proc_data = []

    def refresh_processes(self):
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._refresh_processes_worker, self._refresh_processes_done,
                  on_error=lambda exc: self._generic_error("procesos", exc))

    def _refresh_processes_worker(self):
        return (get_processes(),)

    def _refresh_processes_done(self, procs):
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
        self.app.log(f"Procesos: {count} mostrados.")

    def on_busy(self, busy):
        state = "disabled" if busy else "normal"
        for btn in (self.tasks_refresh_btn, self.tasks_disable_btn,
                    self.tasks_enable_btn, self.proc_refresh_btn, self.kill_btn):
            btn.configure(state=state)

    def _generic_error(self, area, exc):
        self.app.set_busy(False)
        self.app.set_status(f"Error al cargar {area}")
        self.app.log(f"Error en {area}: {exc}")
        messagebox.showerror(APP_NAME, f"Error al cargar {area}:\n{exc}")

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


