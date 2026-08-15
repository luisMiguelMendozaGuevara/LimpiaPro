"""Pagina: Limpieza."""

import customtkinter as ctk

from ..recycle import recycle_bin_size
from ..utils import format_size
from ..winstyle import fluent_font


class CleanPage(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.vars = {}
        self.size_labels = {}
        self.count_labels = {}

        ctk.CTkLabel(self, text="Limpieza del sistema",
                     font=fluent_font(20, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
        ctk.CTkLabel(self, text="Selecciona lo que quieres limpiar. Nada se elimina sin tu confirmacion.",
                     font=fluent_font(12), text_color=("gray40", "gray60")).pack(anchor="w", padx=16)

        self.toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=16, pady=(10, 4))
        accent = getattr(self.app, "accent", "#0067c0")
        ctk.CTkButton(self.toolbar, text="Seleccionar todo", width=130,
                      command=lambda: self.toggle_all(True)).pack(side="left")
        ctk.CTkButton(self.toolbar, text="Ninguno", width=90,
                      command=lambda: self.toggle_all(False)).pack(side="left", padx=8)
        ctk.CTkButton(self.toolbar, text="Vista previa", width=110,
                      command=self.app.preview_clean).pack(side="left")
        ctk.CTkButton(self.toolbar, text="Reglas winapp2...", width=130,
                      command=self.app.load_winapp_rules).pack(side="left", padx=8)
        self.clean_btn = ctk.CTkButton(self.toolbar, text="Limpiar seleccionado", width=170,
                                       fg_color=accent, hover_color=accent,
                                       command=self.app.confirm_clean)
        self.clean_btn.pack(side="right")

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=("gray92", "#1c1c1e"))
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=6)
        self._build_rows()

        self.total_frame = ctk.CTkFrame(self, fg_color=("gray90", "#18181a"))
        self.total_frame.pack(fill="x", padx=16, pady=(2, 8))
        self.total_lbl = ctk.CTkLabel(self.total_frame, text="Total seleccionado: calculando...",
                                      font=fluent_font(13, "bold"))
        self.total_lbl.pack(side="left", padx=12, pady=6)
        self.progress = ctk.CTkProgressBar(self.total_frame, height=10, mode="determinate",
                                           progress_color=accent)
        self.progress.set(0)
        self.progress.pack(side="left", fill="x", expand=True, padx=12, pady=6)
        self.status_lbl = ctk.CTkLabel(self.total_frame, text="Listo", text_color=("gray40", "gray60"))
        self.status_lbl.pack(side="right", padx=12)

    def _build_rows(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for cat in self.app.categories:
            row = ctk.CTkFrame(self.list_frame, corner_radius=10)
            row.pack(fill="x", pady=3)

            var = ctk.BooleanVar(value=True)
            self.vars[cat.key] = var
            cb = ctk.CTkCheckBox(row, text="", variable=var, width=28,
                                 fg_color=getattr(self.app, "accent", "#0067c0"),
                                 hover_color=getattr(self.app, "accent", "#0067c0"),
                                 command=self.app.update_total)
            cb.grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=6)

            ctk.CTkLabel(row, text=cat.icon, font=ctk.CTkFont(size=18)).grid(row=0, column=1, rowspan=2, padx=4)

            ctk.CTkLabel(row, text=cat.label, font=fluent_font(14, "bold")).grid(row=0, column=2, sticky="w")
            admin = "  [requiere administrador]" if cat.needs_admin else ""
            ctk.CTkLabel(row, text=cat.description + admin,
                         font=fluent_font(11), text_color=("gray40", "gray60")).grid(row=1, column=2, sticky="w")

            right = ctk.CTkFrame(row, fg_color="transparent")
            right.grid(row=0, column=3, rowspan=2, padx=10, sticky="e")
            size_lbl = ctk.CTkLabel(right, text="calculando...", font=fluent_font(12, "bold"),
                                    text_color="#2e9e5b")
            size_lbl.pack(side="right")
            count_lbl = ctk.CTkLabel(right, text="", font=fluent_font(10),
                                     text_color=("gray50", "gray50"))
            count_lbl.pack(side="right", padx=(0, 10))
            self.size_labels[cat.key] = size_lbl
            self.count_labels[cat.key] = count_lbl
            self.list_frame.rowconfigure(1, weight=1)

    def toggle_all(self, value):
        for var in self.vars.values():
            var.set(value)
        self.app.update_total()

    def update_after_scan(self, cat):
        if cat.recycle_bin:
            size = recycle_bin_size()
            txt = f"~{format_size(size)}" if size else "papelera vacia"
            self.size_labels[cat.key].configure(text=txt)
            self.count_labels[cat.key].configure(text="")
        else:
            self.size_labels[cat.key].configure(
                text=format_size(cat.size) if cat.size else "limpio")
            self.count_labels[cat.key].configure(
                text=f"{cat.files:,} archivos" if cat.files else "")
