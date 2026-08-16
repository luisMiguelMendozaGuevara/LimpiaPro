"""Centralized theme: shared colors and UI helpers.

Keeping the palette here avoids the same literals drifting apart across
pages; the accent fallback matches the one winstyle reads from Windows."""

import customtkinter as ctk

from ..winstyle import fluent_font

# Default accent color (used when the system accent cannot be read).
ACCENT_FALLBACK = "#0067c0"

# Status palette reused across every page.
ORANGE = "#e65100"
ORANGE_HOVER = "#ef6c00"
GREEN = "#2e7d32"
GREEN_HOVER = "#388e3c"
GREEN_TEXT = "#2e9e5b"
RED = "#c62828"
RED_HOVER = "#d32f2f"

# Muted text color valid in both light and dark modes.
MUTED = ("gray40", "gray60")


def page_header(parent, title, subtitle, size=20):
    """Standard page header: large title + muted subtitle."""
    ctk.CTkLabel(parent, text=title,
                 font=fluent_font(size, "bold")).pack(anchor="w", padx=16, pady=(12, 2))
    ctk.CTkLabel(parent, text=subtitle, font=fluent_font(12),
                 text_color=MUTED).pack(anchor="w", padx=16)
