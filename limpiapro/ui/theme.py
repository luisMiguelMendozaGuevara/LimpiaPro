"""PySide6 visual theme: color palettes, accent resolution and QSS."""

from __future__ import annotations

import ctypes
import os

# Dark and light palettes; the QSS references these as %TOKEN% placeholders.
DARK = {
    "BG": "#1e1f24",
    "SIDEBAR": "#17181c",
    "CARD": "#26272e",
    "CARD_ALT": "#24252b",
    "CARD_HOVER": "#2b2d34",
    "BORDER": "#2f3138",
    "TEXT": "#e8eaed",
    "MUTED": "#9aa0a6",
    "FAINT": "#6b7280",
    "INPUT": "#2f3138",
    "SUCCESS": "#34a853",
    "ERROR": "#ea4335",
    "ERROR_SOFT": "#3a2a2c",
    "ERROR_SOFT_HOVER": "#4a3235",
    "ERROR_BORDER": "#5a3a3d",
}

LIGHT = {
    "BG": "#f3f4f6",
    "SIDEBAR": "#e8eaed",
    "CARD": "#ffffff",
    "CARD_ALT": "#f7f8fa",
    "CARD_HOVER": "#eef0f3",
    "BORDER": "#d7dade",
    "TEXT": "#1f2328",
    "MUTED": "#5f6672",
    "FAINT": "#8b929c",
    "INPUT": "#e4e6ea",
    "SUCCESS": "#1e8e3e",
    "ERROR": "#d93025",
    "ERROR_SOFT": "#fde8e8",
    "ERROR_SOFT_HOVER": "#fbd3d3",
    "ERROR_BORDER": "#f0b6b6",
}

ACCENT_FALLBACK = "#4f8ef7"

_STYLE_PATH = os.path.join(os.path.dirname(__file__), "resources", "style.qss")


def get_system_accent() -> str:
    """Windows accent color (DwmGetColorizationColor) as #rrggbb, with a
    fallback when the API is unavailable. Duplicated from winstyle.py
    without the tkinter/customtkinter dependencies."""
    try:
        color = ctypes.c_uint32()
        opaque = ctypes.c_int()
        ok = ctypes.windll.dwmapi.DwmGetColorizationColor(
            ctypes.byref(color), ctypes.byref(opaque))
        if ok == 0:
            rgb = color.value & 0x00FFFFFF
            return f"#{rgb:06x}"
    except Exception:
        pass
    return ACCENT_FALLBACK


def system_is_dark() -> bool:
    """Windows app theme: True for dark. Registry Personalize key."""
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            value, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
            return value == 0
    except OSError:
        return True  # dark-first fallback


def _hover(hex_color: str) -> str:
    """Lighten a #rrggbb color for hover states."""
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return hex_color
    lift = 18
    return f"#{min(r + lift, 255):02x}{min(g + lift, 255):02x}{min(b + lift, 255):02x}"


def palette(dark: bool = True) -> dict[str, str]:
    return dict(DARK if dark else LIGHT)


def build_stylesheet(accent: str | None = None, dark: bool = True) -> str:
    """Render the QSS with the palette and accent colors substituted."""
    accent = accent or get_system_accent()
    colors = palette(dark)
    colors["ACCENT"] = accent
    colors["ACCENT_HOVER"] = _hover(accent)
    try:
        with open(_STYLE_PATH, encoding="utf-8") as f:
            qss = f.read()
    except OSError:
        qss = ""
    for token, value in colors.items():
        qss = qss.replace(f"%{token}%", value)
    return qss


def apply_theme(app, accent: str | None = None, dark: bool | None = None) -> str:
    """Apply the stylesheet to a QApplication; returns the accent used.

    `dark` None resolves the system theme (Windows app theme)."""
    accent = accent or get_system_accent()
    if dark is None:
        dark = system_is_dark()
    app.setStyleSheet(build_stylesheet(accent, dark))
    return accent
