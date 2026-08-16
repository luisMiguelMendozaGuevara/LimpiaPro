"""Tema centralizado: colores y helpers compartidos de la interfaz."""

import customtkinter as ctk

from ..winstyle import fluent_font

# Color de acento por defecto (si no se lee el del sistema).
ACCENT_FALLBACK = "#0067c0"

# Paleta de estado reutilizada en todas las paginas.
ORANGE = "#e65100"
ORANGE_HOVER = "#ef6c00"
GREEN = "#2e7d32"
GREEN_HOVER = "#388e3c"
GREEN_TEXT = "#2e9e5b"
RED = "#c62828"
RED_HOVER = "#d32f2f"

# Color de texto atenuado en ambos modos.
MUTED = ("gray40", "gray60")


def page_header(parent, title, subtitle, size=20):
    """Cabecera estandar de pagina: titulo grande + subtitulo atenuado."""
    ctk.CTkLabel(parent, text=title,
                 font=fluent_font(size, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
    ctk.CTkLabel(parent, text=subtitle, font=fluent_font(12),
                 text_color=MUTED).pack(anchor="w", padx=16)
