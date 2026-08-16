"""Pagina: Desinstalador."""

from tkinter import messagebox

import customtkinter as ctk

from .. import APP_NAME
from ..uninstall import (delete_registry_path, find_leftovers,
                         get_installed_apps, launch_uninstaller)
from ..utils import _delete_path, format_size
from .theme import MUTED, ORANGE, ORANGE_HOVER, RED, RED_HOVER, page_header
from .widgets import fill_tree, make_tree, readonly_toplevel, run_async, selected_one


class UninstallPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        page_header(self, "Desinstalador",
                    "Desinstala programas y busca restos dejados en disco y registro.")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(10, 4))
        self.refresh_btn = ctk.CTkButton(bar, text="Refrescar", width=100,
                                         command=self.refresh)
        self.refresh_btn.pack(side="left")
        self.uninstall_btn = ctk.CTkButton(bar, text="Desinstalar", width=120, fg_color=ORANGE, hover_color=ORANGE_HOVER, command=self.uninstall_selected)
        self.uninstall_btn.pack(side="left", padx=8)
        self.search_btn = ctk.CTkButton(bar, text="Buscar restos", width=120,
                                        command=self.search_leftovers)
        self.search_btn.pack(side="left", padx=8)
        self.del_btn = ctk.CTkButton(bar, text="Eliminar restos", width=130, fg_color=RED, hover_color=RED_HOVER, command=self.delete_leftovers)
        self.del_btn.pack(side="left", padx=8)
        self.info = ctk.CTkLabel(bar, text="", text_color=MUTED)
        self.info.pack(side="right", padx=8)

        self.tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.tree_frame.pack(fill="both", expand=True)
        self.tree = make_tree(
            self.tree_frame,
            [("#0", "Aplicacion", 360), ("publisher", "Publicador", 240),
             ("size", "Tamano", 100, "e")])

        self.apps = []
        self.leftovers = []
        self.refresh()

    def refresh(self):
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._load_worker, self._load_done,
                  on_error=self._load_error)

    def _load_worker(self):
        return (get_installed_apps(),)

    def _load_error(self, exc):
        self.app.set_busy(False)
        self.info.configure(text="Error al cargar aplicaciones")
        self.app.log(f"Error cargando aplicaciones: {exc}")

    def _load_done(self, apps):
        self.app.set_busy(False)
        self.apps = apps
        specs = []
        for i, a in enumerate(apps):
            specs.append((str(i), "", a["name"],
                          (a["publisher"],
                           format_size(a["size_kb"] * 1024) if a["size_kb"] else ""),
                          {}))
        fill_tree(self.tree, specs)
        self.info.configure(text=f"{len(apps)} aplicaciones")
        self.app.log(f"Programas instalados: {len(apps)}.")

    def on_busy(self, busy):
        state = "disabled" if busy else "normal"
        for btn in (self.refresh_btn, self.uninstall_btn,
                    self.search_btn, self.del_btn):
            btn.configure(state=state)

    def uninstall_selected(self):
        app = selected_one(self.tree, self.apps)
        if not app:
            return
        if not app["uninstall"]:
            messagebox.showwarning(APP_NAME,
                                   "Esta aplicacion no tiene un comando de desinstalacion.")
            return
        if not messagebox.askyesno(
                APP_NAME,
                f"Ejecutar el desinstalador de:\n\n  {app['name']}\n\n"
                f"{app['uninstall']}\n\nSigue las instrucciones del programa."):
            return
        # Sin shell=True: el comando se divide, se verifica que el ejecutable
        # existe y se lanza con lista de argumentos. Se hace en hilo porque
        # split_command resuelve contra disco (System32/PATH).
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._launch_worker, self._launch_done, (app,),
                  on_error=lambda exc: self._launch_error(app, exc))

    def _launch_worker(self, app):
        return app["name"], *launch_uninstaller(app["uninstall"])

    def _launch_done(self, name, ok, msg):
        self.app.set_busy(False)
        if ok:
            self.app.log(f"Desinstalador lanzado: {name}")
            self.app.set_status(f"Desinstalador lanzado: {name}")
        else:
            self.app.log(f"No se pudo lanzar el desinstalador de {name}: {msg}")
            messagebox.showerror(APP_NAME, f"No se pudo lanzar el desinstalador:\n{msg}")

    def _launch_error(self, app, exc):
        self.app.set_busy(False)
        messagebox.showerror(APP_NAME,
                             f"No se pudo lanzar el desinstalador:\n{exc}")

    def search_leftovers(self):
        app = selected_one(self.tree, self.apps)
        if not app:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._leftover_worker, self._leftover_done, (app,),
                  on_error=self._leftover_error)

    def _leftover_worker(self, app):
        results = find_leftovers(app["name"], app.get("location", ""))
        return app["name"], results

    def _leftover_error(self, exc):
        self.app.set_busy(False)
        self.info.configure(text="")
        messagebox.showerror(APP_NAME, f"Error al buscar restos:\n{exc}")

    def _leftover_done(self, name, results):
        self.app.set_busy(False)
        self.leftovers = results
        self.info.configure(text=f"{name}: {len(results)} restos" if results else "")
        if not results:
            messagebox.showinfo(APP_NAME, f"No se encontraron restos para: {name}")
            return
        self.app.log(f"Restos de {name}: {len(results)} encontrados.")
        win, box = readonly_toplevel(
            self, "Restos encontrados", "680x440",
            f"Restos encontrados para {name} ({len(results)}):")
        box.configure(state="normal")
        box.insert("1.0", "\n".join(f"[{kind}] {p}" for kind, p in results))
        box.configure(state="disabled")

    def delete_leftovers(self):
        if not self.leftovers:
            messagebox.showinfo(APP_NAME, "Primero busca restos con 'Buscar restos'.")
            return
        msg = "Se eliminaran definitivamente:\n\n" + "\n".join(
            f"  {p}" for _, p in self.leftovers[:20])
        if len(self.leftovers) > 20:
            msg += f"\n... y {len(self.leftovers) - 20} mas"
        msg += "\n\nDeseas continuar?"
        if not messagebox.askyesno(APP_NAME, msg, icon="warning"):
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._delete_leftovers_worker, self._delete_leftovers_done,
                  on_error=self._leftover_error)

    def _delete_leftovers_worker(self):
        ok = 0
        err = 0
        for kind, p in self.leftovers:
            deleted = (delete_registry_path(p) if kind == "registro"
                       else _delete_path(p))
            if deleted:
                ok += 1
            else:
                err += 1
        return ok, err

    def _delete_leftovers_done(self, ok, err):
        self.app.set_busy(False)
        self.leftovers = []
        self.info.configure(text="")
        self.app.log(f"Restos eliminados: {ok} OK, {err} errores.")
        self.app.set_status(f"Restos eliminados: {ok} OK, {err} errores.")


