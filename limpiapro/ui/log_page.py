"""Pagina: Registro de actividad."""

import time

import customtkinter as ctk

from ..winstyle import fluent_font


class LogPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        ctk.CTkLabel(self, text="Registro de actividad",
                     font=fluent_font(20, "bold")).pack(anchor="w", padx=16, pady=(12, 6))
        self.text = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12),
                                   wrap="word", fg_color=("#eeeeee", "#111111"))
        self.text.pack(fill="both", expand=True, padx=16, pady=6)
        self.text.configure(state="disabled")

    def log(self, msg):
        self.text.configure(state="normal")
        self.text.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.text.see("end")
        self.text.configure(state="disabled")
