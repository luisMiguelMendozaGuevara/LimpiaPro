"""Pagina: Duplicados."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .. import APP_NAME
from ..duplicates import DuplicateScanner
from ..utils import _delete_path, _safe_size, format_size
from .theme import GREEN, GREEN_HOVER, MUTED, RED, RED_HOVER, page_header
from .widgets import fill_tree, make_tree, run_async


class DuplicatePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        page_header(self, "Archivos duplicados",
                    "Escanea una carpeta y encuentra archivos con el mismo contenido (por hash blake2b).")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=10)
        self.folder_path = ctk.StringVar(value="")
        ctk.CTkButton(bar, text="Elegir carpeta...", width=130, command=self.choose_folder).pack(side="left")
        ctk.CTkEntry(bar, textvariable=self.folder_path, placeholder_text="Ruta a escanear",
                     state="readonly").pack(side="left", fill="x", expand=True, padx=8)
        self.min_size = ctk.StringVar(value="2 MB")
        ctk.CTkLabel(bar, text="TamaÃ±o min:").pack(side="left")
        ctk.CTkOptionMenu(bar, values=["1 MB", "2 MB", "5 MB", "10 MB", "50 MB"],
                          variable=self.min_size, width=90).pack(side="left", padx=6)
        self.scan_btn = ctk.CTkButton(bar, text="Buscar duplicados", width=140,
                                      fg_color=GREEN,
                                      hover_color=GREEN_HOVER, command=self.start_scan)
        self.scan_btn.pack(side="left", padx=6)

        self.info = ctk.CTkLabel(self, text="", text_color=MUTED)
        self.info.pack(anchor="w", padx=16)

        self.tree_frame = ctk.CTkFrame(self, fg_color=("gray92", "#1c1c1e"))
        self.tree_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self.tree = make_tree(
            self.tree_frame,
            [("#0", "Archivo / grupo", 560), ("dup", "Copias", 70, "center"),
             ("size", "Tamano", 90, "e")])

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(4, 10))
        sel_help = ctk.CTkLabel(bottom, text="Marca los duplicados en el arbol (Ctrl+clic para varios)\ny pulsa Eliminar seleccionados.",
                                font=ctk.CTkFont(size=11), text_color=MUTED)
        sel_help.pack(side="left")
        self.summary = ctk.CTkLabel(bottom, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.summary.pack(side="left", padx=12)
        self.delete_btn = ctk.CTkButton(bottom, text="Eliminar seleccionados", width=180,
                                        fg_color=RED, hover_color=RED_HOVER,
                                        command=self.delete_selected)
        self.delete_btn.pack(side="right")

    def on_busy(self, busy):
        state = "disabled" if busy else "normal"
        self.scan_btn.configure(state=state)
        self.delete_btn.configure(state=state)

    def choose_folder(self):
        path = filedialog.askdirectory(title="Selecciona la carpeta a escanear")
        if path:
            self.folder_path.set(path)

    def _tree_path(self, item_id):
        """Devuelve la ruta de archivo de un item del arbol, o None."""
        label = self.tree.item(item_id, "text")
        if not label or label.startswith("(") or label.endswith(")"):
            return None
        if self.tree.parent(item_id) == "":
            return None  # es un grupo, no un archivo
        return label

    def start_scan(self):
        if self.app.busy:
            return
        folder = self.folder_path.get()
        if not folder:
            messagebox.showinfo(APP_NAME, "Selecciona una carpeta primero.")
            return
        min_mb = int(self.min_size.get().split()[0])
        self.app.set_status(f"Buscando duplicados en {folder} ...")
        self.app.set_busy(True, mode="indeterminate")
        self.app.scanner = DuplicateScanner(folder, min_mb)
        self.tree.delete(*self.tree.get_children())
        self.summary.configure(text="Escaneando...")
        self.info.configure(text="")
        self._scan_folder = folder
        run_async(self.app, self._scan_worker, self._done, (folder,),
                  on_error=self._scan_error)

    def _scan_worker(self, folder):
        return self.app.scanner.scan(), None

    def _scan_error(self, exc):
        self.app.set_busy(False)
        self.summary.configure(text="")
        self.app.set_status("Busqueda fallo")
        self.app.log(f"Error en duplicados: {exc}")
        messagebox.showerror(APP_NAME, f"Error: {exc}")

    def _done(self, groups, error):
        self.app.set_busy(False)
        if error:
            self.summary.configure(text="")
            self.app.set_status("Busqueda fallo")
            self.app.log(f"Error en duplicados: {error}")
            messagebox.showerror(APP_NAME, f"Error: {error}")
            return
        self.tree.delete(*self.tree.get_children())
        if not groups:
            self.app.set_status("No se encontraron duplicados")
            self.summary.configure(text="No se encontraron archivos duplicados.")
            self.info.configure(text="")
            return
        dup_count = sum(len(g) - 1 for g in groups)
        wasted = sum(_safe_size(g[0]) * (len(g) - 1) for g in groups)
        self.summary.configure(
            text=f"{len(groups)} grupos duplicados  \u00b7  {format_size(wasted)} recuperables")
        self.info.configure(text=f"Resultados de: {self.folder_path.get()}")
        specs = []
        for gi, group in enumerate(groups):
            gid = f"g{gi}"
            head = (f"{os.path.basename(group[0])}  \u00b7  "
                    f"{format_size(_safe_size(group[0]))}")
            specs.append((gid, "", head, (str(len(group)), ""), {"open": False}))
            specs.append(("", gid, "(original, mantenido)", ("", ""), {}))
            for dup in group[1:]:
                specs.append(("", gid, dup, ("", ""), {}))
        fill_tree(self.tree, specs)
        self.app.set_status(f"Busqueda finalizada: {len(groups)} grupos de duplicados")
        self.app.log(f"Duplicados en {self.folder_path.get()}: {len(groups)} grupos, "
                     f"{dup_count} archivos, {format_size(wasted)} desperdiciados.")

    def delete_selected(self):
        selected = [self._tree_path(i) for i in self.tree.selection()]
        paths = [p for p in selected if p]
        if not paths:
            messagebox.showinfo(APP_NAME,
                                "Selecciona archivos duplicados en el arbol (los que estan debajo de cada grupo).\n"
                                "El original se mantiene.")
            return
        msg = "Se eliminaran definitivamente estos archivos:\n\n" + "\n".join(paths[:15])
        if len(paths) > 15:
            msg += f"\n... y {len(paths) - 15} mas"
        msg += f"\n\n({format_size(sum(_safe_size(p) for p in paths))} a liberar)\n\nContinuar?"
        if not messagebox.askyesno(APP_NAME, msg, icon="warning"):
            return
        self.app.set_busy(True, mode="indeterminate")
        run_async(self.app, self._delete_worker, self._delete_done, (paths,))

    def _delete_worker(self, paths):
        removed = 0
        errors = 0
        for p in paths:
            if os.path.exists(p):
                if _delete_path(p):
                    removed += 1
                else:
                    errors += 1
        return removed, errors

    def _delete_done(self, removed, errors):
        self.app.set_busy(False)
        self.app.set_status(f"Duplicados eliminados: {removed}, errores: {errors}")
        self.app.log(f"Eliminados {removed} duplicados ({errors} errores).")
        # borrar del arbol los items eliminados
        for item_id in self.tree.get_children():
            for child in self.tree.get_children(item_id):
                p = self._tree_path(child)
                if p and not os.path.exists(p):
                    self.tree.delete(child)
        messagebox.showinfo(APP_NAME, f"Se eliminaron {removed} archivos duplicados.")

