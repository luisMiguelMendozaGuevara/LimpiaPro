"""Pagina: Restos de Windows Update (WinSxS / DISM)."""

import subprocess

import customtkinter as ctk
from tkinter import messagebox
from .. import APP_NAME
from ..utils import _folder_size, format_size
from .theme import MUTED, ORANGE, ORANGE_HOVER, page_header
from .widgets import run_async


class UpdatePage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        page_header(self, "Restos de Windows Update",
                    "Limpia componentes antiguos (WinSxS) y versiones previas de "
                    " actualizaciones. Requiere administrador.")

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(10, 4))
        self.analyze_btn = ctk.CTkButton(bar, text="Analizar", width=110,
                                         command=self.analyze)
        self.analyze_btn.pack(side="left")
        self.clean_btn = ctk.CTkButton(bar, text="Limpiar actualizaciones", width=190,
                                       fg_color=ORANGE, hover_color=ORANGE_HOVER,
                                       command=self.clean)
        self.clean_btn.pack(side="left", padx=8)
        self.size_lbl = ctk.CTkLabel(bar, text="calculando...", text_color=MUTED)
        self.size_lbl.pack(side="right", padx=8)

        self.out = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=11),
                                  wrap="word", fg_color=("#eeeeee", "#111111"))
        self.out.pack(fill="both", expand=True, padx=16, pady=8)
        self.out.configure(state="disabled")

        run_async(self.app, self._measure, self._measure_done,
              on_error=lambda exc: self._measure_error(exc))

    def _measure_error(self, exc):
        self.app.set_busy(False)
        self.size_lbl.configure(text="no disponible")
        self.app.log(f"Error midiendo WinSxS: {exc}")

    def _log_out(self, text):
        self.out.configure(state="normal")
        self.out.insert("end", text + "\n")
        self.out.see("end")
        self.out.configure(state="disabled")

    def _measure(self):
        return (_folder_size(r"C:\Windows\WinSxS"),)

    def _measure_done(self, size):
        self.size_lbl.configure(text=f"Tienda WinSxS: {format_size(size)}")

    def _run_dism(self, args, label):
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        self._log_out(f">> {label}")
        run_async(self.app, self._dism_worker, self._dism_done, (args,),
                  on_error=lambda exc: self._dism_error(exc))

    def _dism_error(self, exc):
        self.app.set_busy(False)
        self._log_out(f"Error: {exc}")

    def on_busy(self, busy):
        state = "disabled" if busy else "normal"
        self.analyze_btn.configure(state=state)
        self.clean_btn.configure(state=state)

    def _dism_worker(self, args):
        try:
            result = subprocess.run(
                ["dism", "/online", "/cleanup-image"] + args,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=1800, creationflags=subprocess.CREATE_NO_WINDOW)
            out = (result.stdout or result.stderr or "").strip()
        except Exception as e:
            out = f"Error: {e}"
        return (out,)

    def _dism_done(self, out):
        self.app.set_busy(False)
        self._log_out(out or "(sin salida)")
        self._log_out(">> Terminado.")

    def analyze(self):
        self._run_dism(["/AnalyzeComponentStore"], "Analizando tienda de componentes...")

    def clean(self):
        if not messagebox.askyesno(
                APP_NAME,
                "Se eliminaran versiones anteriores de actualizaciones de Windows.\n\n"
                "El proceso puede tardar varios minutos (DISM).\n\nContinuar?"):
            return
        self._run_dism(["/StartComponentCleanup"], "Limpiando componentes antiguos...")

