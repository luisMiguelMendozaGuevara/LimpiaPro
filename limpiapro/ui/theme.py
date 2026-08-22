"""PySide6 theme: a faithful replica of the legacy customtkinter look.

The palette below mirrors limpiapro/ui/legacy_tk/theme.py and the colors
used across the legacy pages (root/sidebar/list backgrounds, the status
colors GREEN/ORANGE/RED and the muted text), so the migrated interface
looks the same. The stylesheet is rendered from resources/style.qss with
%TOKEN% placeholders substituted at runtime (dark/light + accent)."""

from __future__ import annotations

import ctypes
import os

# Status palette (identical to the legacy theme).
ORANGE = "#e65100"
ORANGE_HOVER = "#ef6c00"
GREEN = "#2e7d32"
GREEN_HOVER = "#388e3c"
GREEN_TEXT = "#2e9e5b"
RED = "#c62828"
RED_HOVER = "#d32f2f"
MUTED = "#9aa0a6"
ACCENT_FALLBACK = "#0067c0"

DARK = {
    "BG": "#17181c",           # root window
    "SIDEBAR": "#222327",
    "CARD": "#1c1c1e",         # lists / scroll frame
    "CARD_ALT": "#18181a",
    "CARD_HOVER": "#2e2f35",   # nav hover
    "BORDER": "#2f3138",
    "TEXT": "#dce4ee",
    "MUTED": "#9aa0a6",
    "FAINT": "#6b7280",
    "INPUT": "#2b2d33",
    "CONSOLE": "#111111",      # readonly textboxes
    "SUCCESS": GREEN,
    "SUCCESS_TEXT": GREEN_TEXT,
    "WARNING": ORANGE,
    "ERROR": RED,
    "ERROR_SOFT": "#3a2626",
    "ERROR_SOFT_HOVER": "#4a2f2f",
    "ERROR_BORDER": "#5a3a3d",
    "WARNING_SOFT": "#3a2d1e",
    "WARNING_SOFT_HOVER": "#4a3a26",
    "WARNING_BORDER": "#5a4630",
}

LIGHT = {
    "BG": "#e8e8e8",
    "SIDEBAR": "#d9d9d9",
    "CARD": "#f5f5f5",
    "CARD_ALT": "#f0f0f0",
    "CARD_HOVER": "#c3c3c3",
    "BORDER": "#c9c9c9",
    "TEXT": "#1a1a1a",
    "MUTED": "#5f6672",
    "FAINT": "#8b929c",
    "INPUT": "#e2e2e2",
    "CONSOLE": "#eeeeee",
    "SUCCESS": GREEN,
    "SUCCESS_TEXT": GREEN,
    "WARNING": ORANGE,
    "ERROR": RED,
    "ERROR_SOFT": "#f4dada",
    "ERROR_SOFT_HOVER": "#eec4c4",
    "ERROR_BORDER": "#e0b3b3",
    "WARNING_SOFT": "#f6e3cf",
    "WARNING_SOFT_HOVER": "#efd5b8",
    "WARNING_BORDER": "#e3c29b",
}

_STYLE_PATH = os.path.join(os.path.dirname(__file__), "resources", "style.qss")


def get_system_accent() -> str:
    """Windows accent color (DwmGetColorizationColor) as #rrggbb, with a
    fallback matching the legacy ACCENT_FALLBACK."""
    try:
        color = ctypes.c_uint32()
        opaque = ctypes.c_int()
        ok = ctypes.windll.dwmapi.DwmGetColorizationColor(
            ctypes.byref(color), ctypes.byref(opaque))
        if ok == 0:
            return f"#{color.value & 0x00FFFFFF:06x}"
    except Exception:
        pass
    return ACCENT_FALLBACK


def system_is_dark() -> bool:
    """Windows app theme: True for dark."""
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
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return hex_color
    lift = 14
    return f"#{min(r + lift, 255):02x}{min(g + lift, 255):02x}{min(b + lift, 255):02x}"


def palette(dark: bool = True) -> dict[str, str]:
    return dict(DARK if dark else LIGHT)


def build_stylesheet(accent: str | None = None, dark: bool = True) -> str:
    """Render resources/style.qss with the palette and accent."""
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
    """Apply the replica stylesheet; returns the accent used."""
    accent = accent or get_system_accent()
    if dark is None:
        dark = system_is_dark()
    app.setStyleSheet(build_stylesheet(accent, dark))
    return accent


def apply_mica_backdrop(window) -> bool:
    """Windows 11 Mica for the window frame (best-effort; the solid QSS
    backgrounds carry the look regardless). Returns True when applied."""
    try:
        hwnd = int(window.winId())
        # DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_MAINWINDOW = 2 (Win11 22H2+)
        value = ctypes.c_int(2)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 38, ctypes.byref(value), ctypes.sizeof(value))
        return result == 0
    except Exception:
        return False
