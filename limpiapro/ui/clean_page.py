"""Page: system cleanup.

Shows one row per cleaning category with a checkbox, the measured size and
the file count. The bottom bar holds the selected total, the global
progress bar and the status label used by the whole app."""

import customtkinter as ctk

from ..contracts import CleanerAppProtocol
from ..i18n import t
from ..utils import format_size
from ..winstyle import fluent_font
from .theme import ACCENT_FALLBACK, GREEN_TEXT, MUTED, page_header


class CleanPage(ctk.CTkFrame):
    """Main cleanup page: category checkboxes plus totals and progress."""

    def __init__(self, master, app: CleanerAppProtocol):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.vars = {}
        self.size_labels = {}
        self.count_labels = {}

        page_header(self, t("clean.title"), t("clean.subtitle"))

        self.toolbar = ctk.CTkFrame(self, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=16, pady=(10, 4))
        accent = getattr(self.app, "accent", ACCENT_FALLBACK)
        ctk.CTkButton(
            self.toolbar, text=t("btn.select_all"), width=130, command=lambda: self.toggle_all(True)
        ).pack(side="left")
        ctk.CTkButton(
            self.toolbar, text=t("btn.none"), width=90, command=lambda: self.toggle_all(False)
        ).pack(side="left", padx=8)
        ctk.CTkButton(
            self.toolbar, text=t("btn.preview"), width=110, command=self.app.preview_clean
        ).pack(side="left")
        ctk.CTkButton(
            self.toolbar, text=t("btn.winapp_rules"), width=130, command=self.app.load_winapp_rules
        ).pack(side="left", padx=8)
        self.clean_btn = ctk.CTkButton(
            self.toolbar,
            text=t("btn.clean_selected"),
            width=170,
            fg_color=accent,
            hover_color=accent,
            command=self.app.confirm_clean,
        )
        self.clean_btn.pack(side="right")
        self.cancel_btn = ctk.CTkButton(
            self.toolbar, text=t("btn.cancel"), width=100, command=self.app.request_cancel
        )
        self.cancel_btn.pack(side="right", padx=6)
        self.cancel_btn.configure(state="disabled")

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=("gray92", "#1c1c1e"))
        self.list_frame.pack(fill="both", expand=True, padx=16, pady=6)
        self._build_rows()

        self.total_frame = ctk.CTkFrame(self, fg_color=("gray90", "#18181a"))
        self.total_frame.pack(fill="x", padx=16, pady=(2, 8))
        self.total_lbl = ctk.CTkLabel(
            self.total_frame, text=t("clean.total_calculating"), font=fluent_font(13, "bold")
        )
        self.total_lbl.pack(side="left", padx=12, pady=6)
        self.progress = ctk.CTkProgressBar(
            self.total_frame, height=10, mode="determinate", progress_color=accent
        )
        self.progress.set(0)
        self.progress.pack(side="left", fill="x", expand=True, padx=12, pady=6)
        self.status_lbl = ctk.CTkLabel(self.total_frame, text=t("status.ready"), text_color=MUTED)
        self.status_lbl.pack(side="right", padx=12)

    def _build_rows(self):
        """(Re)build one row per category. Called at construction and again
        after loading winapp2 rules (the category description may change).
        Row widgets are destroyed and rebuilt wholesale."""
        for w in self.list_frame.winfo_children():
            w.destroy()
        accent = getattr(self.app, "accent", ACCENT_FALLBACK)
        for cat in self.app.categories:
            row = ctk.CTkFrame(self.list_frame, corner_radius=10)
            row.pack(fill="x", pady=3)

            var = ctk.BooleanVar(value=True)
            self.vars[cat.key] = var
            cb = ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=28,
                fg_color=accent,
                hover_color=accent,
                command=self.app.update_total,
            )
            cb.grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=6)

            ctk.CTkLabel(row, text=cat.icon, font=ctk.CTkFont(size=18)).grid(
                row=0, column=1, rowspan=2, padx=4
            )

            ctk.CTkLabel(row, text=cat.label, font=fluent_font(14, "bold")).grid(
                row=0, column=2, sticky="w"
            )
            admin = t("clean.needs_admin") if cat.needs_admin else ""
            ctk.CTkLabel(
                row, text=cat.description + admin, font=fluent_font(11), text_color=MUTED
            ).grid(row=1, column=2, sticky="w")

            right = ctk.CTkFrame(row, fg_color="transparent")
            right.grid(row=0, column=3, rowspan=2, padx=10, sticky="e")
            size_lbl = ctk.CTkLabel(
                right,
                text=t("label.calculating"),
                font=fluent_font(12, "bold"),
                text_color=GREEN_TEXT,
            )
            size_lbl.pack(side="right")
            count_lbl = ctk.CTkLabel(
                right, text="", font=fluent_font(10), text_color=("gray50", "gray50")
            )
            count_lbl.pack(side="right", padx=(0, 10))
            self.size_labels[cat.key] = size_lbl
            self.count_labels[cat.key] = count_lbl

        self.list_frame.rowconfigure(1, weight=1)

    def toggle_all(self, value):
        """Check or uncheck every category checkbox and refresh the total."""
        for var in self.vars.values():
            var.set(value)
        self.app.update_total()

    def update_after_scan(self, cat):
        """Refresh the size/count labels of one category after its scan.

        The recycle bin size was already measured by the analysis worker;
        here it is only displayed (no disk access on the UI thread)."""
        if cat.recycle_bin:
            txt = f"~{format_size(cat.size)}" if cat.size else t("clean.recycle_empty")
            self.size_labels[cat.key].configure(text=txt)
            self.count_labels[cat.key].configure(text="")
        else:
            self.size_labels[cat.key].configure(
                text=format_size(cat.size) if cat.size else t("clean.is_clean")
            )
            self.count_labels[cat.key].configure(
                text=t("clean.n_files", n=f"{cat.files:,}") if cat.files else ""
            )

    def on_busy(self, busy):
        """Disable the clean button while any background operation runs;
        enable the cancel button so the busy operation can be stopped."""
        self.clean_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")
