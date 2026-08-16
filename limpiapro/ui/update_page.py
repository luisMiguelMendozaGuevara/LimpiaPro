"""Page: Windows Update leftovers (WinSxS / DISM).

Measures the component store size and runs DISM analyze/cleanup commands
on a worker thread. DISM output arrives in the operating system language
(out of the app's control) and is appended verbatim to the console box."""

import subprocess

import customtkinter as ctk
from tkinter import messagebox

from .. import APP_NAME
from ..i18n import t
from ..utils import _folder_size, format_size
from .theme import MUTED, ORANGE, ORANGE_HOVER, page_header
from .widgets import run_async


class UpdatePage(ctk.CTkFrame):
    """WinSxS component store analyzer and cleaner (DISM wrapper)."""

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app

        page_header(self, t("update.title"), t("update.subtitle"))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(10, 4))
        self.analyze_btn = ctk.CTkButton(bar, text=t("btn.analyze"), width=110,
                                         command=self.analyze)
        self.analyze_btn.pack(side="left")
        self.clean_btn = ctk.CTkButton(bar, text=t("btn.clean_updates"), width=190,
                                       fg_color=ORANGE, hover_color=ORANGE_HOVER,
                                       command=self.clean)
        self.clean_btn.pack(side="left", padx=8)
        self.size_lbl = ctk.CTkLabel(bar, text=t("label.calculating"),
                                     text_color=MUTED)
        self.size_lbl.pack(side="right", padx=8)

        self.out = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=11),
                                  wrap="word", fg_color=("#eeeeee", "#111111"))
        self.out.pack(fill="both", expand=True, padx=16, pady=8)
        self.out.configure(state="disabled")

        # The constructor triggers the WinSxS measurement (the page is built
        # lazily on first visit, so this runs once, off the UI thread).
        run_async(self.app, self._measure, self._measure_done,
                  on_error=lambda exc: self._measure_error(exc))

    def _measure_error(self, exc):
        """Handle a failure of the WinSxS measurement."""
        self.app.set_busy(False)
        self.size_lbl.configure(text=t("update.not_available"))
        self.app.log(t("log.winsxs_error", exc=exc))

    def _log_out(self, text):
        """Append one line to the DISM console box."""
        self.out.configure(state="normal")
        self.out.insert("end", text + "\n")
        self.out.see("end")
        self.out.configure(state="disabled")

    def _measure(self):
        """Walk C:\\Windows\\WinSxS to compute the store size."""
        return (_folder_size(r"C:\Windows\WinSxS"),)

    def _measure_done(self, size):
        """Show the measured component store size."""
        self.size_lbl.configure(text=t("update.winsxs_size",
                                       size=format_size(size)))

    def _run_dism(self, args, label):
        """Guard against concurrent operations and run one DISM command."""
        if self.app.busy:
            return
        self.app.set_busy(True, mode="indeterminate")
        self._log_out(t("update.section", label=label))
        run_async(self.app, self._dism_worker, self._dism_done, (args,),
                  on_error=lambda exc: self._dism_error(exc))

    def _dism_error(self, exc):
        """Handle a DISM worker exception."""
        self.app.set_busy(False)
        self._log_out(t("update.error", exc=exc))

    def on_busy(self, busy):
        """Toggle the analyze/clean buttons."""
        state = "disabled" if busy else "normal"
        self.analyze_btn.configure(state=state)
        self.clean_btn.configure(state=state)

    def _dism_worker(self, args):
        """Run DISM with a 30-minute timeout and return its output.
        Exceptions are converted to text so the console box shows them."""
        try:
            result = subprocess.run(
                ["dism", "/online", "/cleanup-image"] + args,
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=1800, creationflags=subprocess.CREATE_NO_WINDOW)
            out = (result.stdout or result.stderr or "").strip()
        except Exception as e:
            out = t("update.error", exc=e)
        return (out,)

    def _dism_done(self, out):
        """Print the DISM output and mark the operation as finished."""
        self.app.set_busy(False)
        self._log_out(out or t("update.no_output"))
        self._log_out(t("update.finished"))

    def analyze(self):
        """Run the DISM component store analysis."""
        self._run_dism(["/AnalyzeComponentStore"], t("update.analyzing"))

    def clean(self):
        """Confirm and run the DISM component store cleanup."""
        if not messagebox.askyesno(APP_NAME, t("msg.update_clean_confirm")):
            return
        self._run_dism(["/StartComponentCleanup"], t("update.cleaning"))
