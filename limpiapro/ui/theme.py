"""PySide6 theme for LimpiaPro.

The palette below matches the design language used across the pages
(root/sidebar/list backgrounds, the status colors GREEN/ORANGE/RED and
the muted text). The stylesheet is rendered from resources/style.qss with
%TOKEN% placeholders substituted at runtime (dark/light + accent).

Design Principles:
1. Visual Consistency: One design language for the whole interface.
2. Dynamic Theming: Colors are substituted into a QSS template at runtime,
   allowing for dark/light modes and system accent color integration.
3. Native Integration: Uses Windows APIs (DWM) to read system accent colors
   and apply Mica backdrops where supported.
"""

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

# Dark mode palette (default).
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

# Light mode palette.
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

# Font stack: Segoe UI Variable on Windows 11, classic Segoe UI fallback.
FONT_STACK = '"Segoe UI Variable Text", "Segoe UI"'

# Active theme state (kept in sync by build_stylesheet/apply_theme so the
# icon module and pages can recolor themselves).
_active_dark: bool = True
_active_accent: str = ACCENT_FALLBACK

# Rendered-stylesheet cache keyed by (accent, dark): the QSS template is
# read and substituted once per combination instead of per call.
_QSS_CACHE: dict[tuple[str, bool], str] = {}


def get_system_accent() -> str:
    """Windows accent color (DwmGetColorizationColor) as #rrggbb, with a
    fallback matching the legacy ACCENT_FALLBACK.

    Returns:
        str: A hex color string (e.g., "#0067c0").
    """
    try:
        color = ctypes.c_uint32()
        opaque = ctypes.c_int()
        ok = ctypes.windll.dwmapi.DwmGetColorizationColor(
            ctypes.byref(color), ctypes.byref(opaque))
        if ok == 0:
            # Extract RGB from the DWORD (0xAABBGGRR).
            return f"#{color.value & 0x00FFFFFF:06x}"
    except Exception:
        pass
    return ACCENT_FALLBACK


def system_is_dark() -> bool:
    """Windows app theme: True for dark.

    Reads the 'AppsUseLightTheme' registry value to determine the user's
    preferred Windows theme.

    Returns:
        bool: True if the system is in dark mode, False otherwise.
    """
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
    """Generate a lighter hover color by lifting RGB values.

    Args:
        hex_color: A hex color string (e.g., "#0067c0").

    Returns:
        str: A lighter hex color string.
    """
    try:
        r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    except (ValueError, IndexError):
        return hex_color
    lift = 14
    return f"#{min(r + lift, 255):02x}{min(g + lift, 255):02x}{min(b + lift, 255):02x}"


def palette(dark: bool = True) -> dict[str, str]:
    """Return the color palette for the given theme.

    Args:
        dark: True for dark mode, False for light mode.

    Returns:
        dict: A dictionary mapping color tokens to hex values.
    """
    return dict(DARK if dark else LIGHT)


def build_stylesheet(accent: str | None = None, dark: bool = True) -> str:
    """Render resources/style.qss with the palette and accent.

    This function loads the QSS template file and substitutes %TOKEN%
    placeholders with the actual color values.

    Args:
        accent: Optional custom accent color. Defaults to system accent.
        dark: True for dark mode, False for light mode.

    Returns:
        str: The fully rendered QSS stylesheet.
    """
    accent = accent or get_system_accent()
    colors = palette(dark)
    colors["ACCENT"] = accent
    colors["ACCENT_HOVER"] = _hover(accent)
    colors["FONT_STACK"] = FONT_STACK
    cache_key = (accent, dark)
    cached = _QSS_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        with open(_STYLE_PATH, encoding="utf-8") as f:
            qss = f.read()
    except OSError:
        qss = ""
    # Substitute all color tokens in the QSS template.
    for token, value in colors.items():
        qss = qss.replace(f"%{token}%", value)
    _QSS_CACHE[cache_key] = qss
    return qss


def apply_theme(app, accent: str | None = None, dark: bool | None = None) -> str:
    """Apply the replica stylesheet; returns the accent used.

    This is the main entry point for theming the application. It determines
    the appropriate theme (dark/light/system) and applies the rendered
    stylesheet to the QApplication instance.

    Args:
        app: The QApplication instance.
        accent: Optional custom accent color.
        dark: Optional explicit dark/light flag. None means auto-detect.

    Returns:
        str: The accent color that was actually applied.
    """
    accent = accent or get_system_accent()
    if dark is None:
        dark = system_is_dark()
    global _active_dark, _active_accent
    _active_dark = dark
    _active_accent = accent
    # Keep the SVG icon palette in sync with the applied theme.
    from . import icons
    icons.set_icon_theme(dark)
    app.setStyleSheet(build_stylesheet(accent, dark))
    return accent


def apply_mica_backdrop(window) -> bool:
    """Windows 11 Mica for the window frame (best-effort; the solid QSS
    backgrounds carry the look regardless). Returns True when applied.

    This uses the DwmSetWindowAttribute API with the undocumented
    DWMWA_SYSTEMBACKDROP_TYPE attribute (value 38) to enable the Mica
    material on the window frame.

    Args:
        window: A PySide6 QWidget or QMainWindow.

    Returns:
        bool: True if Mica was successfully applied, False otherwise.
    """
    try:
        hwnd = int(window.winId())
        # DWMWA_SYSTEMBACKDROP_TYPE = 38, DWMSBT_MAINWINDOW = 2 (Win11 22H2+)
        value = ctypes.c_int(2)
        result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 38, ctypes.byref(value), ctypes.sizeof(value))
        return result == 0
    except Exception:
        return False
