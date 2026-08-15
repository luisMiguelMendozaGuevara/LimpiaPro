"""Pagina: Desinstalador."""

from tkinter import messagebox

import customtkinter as ctk

from .. import APP_NAME
from ..uninstall import (delete_registry_path, find_leftovers,
                         get_installed_apps, launch_uninstaller)
from ..utils import _delete_path, format_size
from ..winstyle import fluent_font
from .widgets import make_tree, run_async, selected_one


class UninstallPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        ctk.CTkLabel(self, text="Desinstalador",
                     font=fluent_font(20, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(self, text="Desinstala programas y busca restos dejados en disco y registro.",
                     font=fluent_font(12), text_color=("gray40", "gray60")).pack(anchor="w", padx=16)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkButton(bar, text="Refrescar", width=100, command=self.refresh).pack(side="left")
        self.uninstall_btn = ctk.CTkButton(bar, text="Desinstalar", width=120, fg_color="#e65100",
                                           hover_color="#ef6c00", command=self.uninstall_selected)
        self.uninstall_btn.pack(side="left", padx=8)
        ctk.CTkButton(bar, text="Buscar restos", width=120, command=self.search_leftovers).pack(side="left", padx=8)
        self.del_btn = ctk.CTkButton(bar, text="Eliminar restos", width=130, fg_color="#c62828",
                                     hover_color="#d32f2f", command=self.delete_leftovers)
        self.del_btn.pack(side="left", padx=8)
        self.info = ctk.CTkLabel(bar, text="", text_color=("gray40", "gray60"))
        self.info.pack(side="right", padx=8)

        self.tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.tree_frame.pack(fill="both", expand=True)
        self.tree = make_tree(
            self.tree_frame,
            [("#0", "Aplicacion", 360), ("publisher", "Publicador", 240),
             ("size", "Tamano", 100, "e")])
        self.app._restyle_tree()

        self.apps = []
        self.leftovers = []
        self.refresh()

    def refresh(self):
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._load_worker, self._load_done)

    def _load_worker(self):
        return (get_installed_apps(),)

    def _load_done(self, apps):
        self.app.set_busy(False)
        self.apps = apps
        for item in self.tree.get_children():
            self.tree.delete(item)
        for i, a in enumerate(apps):
            self.tree.insert("", "end", iid=str(i), text=a["name"],
                             values=(a["publisher"],
                                     format_size(a["size_kb"] * 1024) if a["size_kb"] else ""))
        self.info.configure(text=f"{len(apps)} aplicaciones")
        self.app.log(f"Programas instalados: {len(apps)}.")

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
        # existe y se lanza con lista de argumentos.
        ok, msg = launch_uninstaller(app["uninstall"])
        if ok:
            self.app.log(f"Desinstalador lanzado: {app['name']}")
            self.app.set_status(f"Desinstalador lanzado: {app['name']}")
        else:
            messagebox.showerror(APP_NAME, f"No se pudo lanzar el desinstalador:\n{msg}")

    def search_leftovers(self):
        app = selected_one(self.tree, self.apps)
        if not app:
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._leftover_worker, self._leftover_done, (app,))

    def _leftover_worker(self, app):
        results = find_leftovers(app["name"], app.get("location", ""))
        return app["name"], results

    def _leftover_done(self, name, results):
        self.app.set_busy(False)
        self.leftovers = results
        self.info.configure(text=f"{name}: {len(results)} restos" if results else "")
        if not results:
            messagebox.showinfo(APP_NAME, f"No se encontraron restos para: {name}")
            return
        self.app.log(f"Restos de {name}: {len(results)} encontrados.")
        win = ctk.CTkToplevel(self)
        win.title("Restos encontrados")
        win.geometry("680x440")
        ctk.CTkLabel(win, text=f"Restos encontrados para {name} ({len(results)}):",
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=("gray30", "gray70")).pack(anchor="w", padx=14, pady=(10, 2))
        box = ctk.CTkTextbox(win, font=ctk.CTkFont(family="Consolas", size=11))
        box.pack(fill="both", expand=True, padx=14, pady=6)
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
        run_async(self.app, self._delete_leftovers_worker, self._delete_leftovers_done)

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
