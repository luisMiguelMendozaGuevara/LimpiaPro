"""Page: activity log."""

import time

import customtkinter as ctk

from ..contracts import CleanerAppProtocol
from ..i18n import t
from ..winstyle import fluent_font


class LogPage(ctk.CTkFrame):
    """Readonly monospace view of everything the app has done this session.

    app.log() forwards every message here; each line is timestamped with
    HH:MM:SS. The textbox is flipped to 'normal' only while inserting."""

    def __init__(self, master, app: CleanerAppProtocol):
        super().__init__(master, fg_color="transparent")
        self.app = app
        ctk.CTkLabel(self, text=t("logpage.title"), font=fluent_font(20, "bold")).pack(
            anchor="w", padx=16, pady=(12, 6)
        )
        self.text = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            fg_color=("#eeeeee", "#111111"),
        )
        self.text.pack(fill="both", expand=True, padx=16, pady=6)
        self.text.configure(state="disabled")

    def log(self, msg):
        """Append one timestamped line to the log view."""
        self.text.configure(state="normal")
        self.text.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.text.see("end")
        self.text.configure(state="disabled")
