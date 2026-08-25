"""Themed SVG icon system for the PySide6 UI.

Icons are Fluent/Lucide-style stroke SVGs rendered at runtime with
QSvgRenderer and recolored from the active palette tokens, so they
follow the dark/light theme and the system accent color without any
external asset files.

Usage:
    from .. import icons
    btn.setIcon(icons.icon("search"))
    nav_btn.setIcon(icons.nav("clean"))   # white variant when checked
    icons.apply(widget, "refresh")        # set icon + standard size

Design Principles:
1. Theme-aware: every icon is re-renderable when the theme changes
   (set_icon_theme clears the cache; pages refresh via refresh_icons()).
2. Cached: each (name, color) pair is rendered once per process.
3. Zero assets: SVG path data lives in this module, so packaging stays
   a pure-Python affair.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# --------------------------------------------------------------------------
# Icon path data (24x24 viewBox, stroke-based)
# --------------------------------------------------------------------------

_ICONS: dict[str, str] = {
    # navigation
    "clean": (
        '<path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 '
        '0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .963 '
        '0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.581a.5.5 0 0 1 0 '
        '.964L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 '
        '1-.963 0z"/>'
        '<path d="M20 3v4"/><path d="M22 5h-4"/>'
    ),
    "startup": (
        '<path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09'
        '-2.91a2.18 2.18 0 0 0-2.91-.09z"/>'
        '<path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72'
        '-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>'
        '<path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/>'
        '<path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>'
    ),
    "dupes": (
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>'
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>'
    ),
    "update": (
        '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
        '<polyline points="7 10 12 15 17 10"/>'
        '<line x1="12" x2="12" y1="15" y2="3"/>'
    ),
    "uninstall": (
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 '
        '8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
        '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'
    ),
    "log": (
        '<polyline points="4 17 10 11 4 5"/><line x1="12" x2="20" y1="19" y2="19"/>'
    ),
    "zap": (
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
    ),
    # actions
    "scan": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "preview": (
        '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "cancel": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "select_all": (
        '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="m9 12 2 2 4-4"/>'
    ),
    "select_none": '<rect width="18" height="18" x="3" y="3" rx="2"/>',
    "folder": (
        '<path d="m6 14 1.5-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.54 '
        '6a2 2 0 0 1-1.95 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 '
        '1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>'
    ),
    "refresh": (
        '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>'
        '<path d="M21 3v5h-5"/>'
        '<path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>'
        '<path d="M8 16H3v5"/>'
    ),
    "delete": (
        '<path d="M3 6h18"/>'
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>'
        '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
    ),
    "disable": (
        '<rect x="14" y="4" width="4" height="16" rx="1"/>'
        '<rect x="6" y="4" width="4" height="16" rx="1"/>'
    ),
    "enable": '<path d="M7 5v14l11-7z"/>',
    "analyze": (
        '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>'
    ),
    "shield": (
        '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 '
        '18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1 1 0 0 1 1.52 '
        '0C14.5 3.8 17 5 19 5a1 1 0 0 1 1 1z"/>'
    ),
    "file": (
        '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>'
        '<path d="M14 2v4a2 2 0 0 0 2 2h4"/>'
    ),
    "globe": (
        '<circle cx="12" cy="12" r="10"/>'
        '<path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 '
        '0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/><path d="M2 12h20"/>'
    ),
    "trash": (
        '<path d="M3 6h18"/>'
        '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>'
        '<path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
    ),
    "gear": (
        '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 '
        '2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 '
        '2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0'
        '-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 '
        '0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 '
        '1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 '
        '0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15'
        '-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 '
        '0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>'
        '<circle cx="12" cy="12" r="3"/>'
    ),
    "history": (
        '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>'
        '<path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>'
    ),
    "package": (
        '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 '
        '8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/>'
        '<path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>'
    ),
}

# Category key -> icon name (clean page rows).
CATEGORY_ICONS: dict[str, str] = {
    "temp": "file",
    "browser": "globe",
    "recycle": "trash",
    "apps": "gear",
    "history": "history",
    "winapp": "package",
}

# Page key -> icon name (sidebar).
NAV_ICONS: dict[str, str] = {
    "clean": "clean",
    "startup": "startup",
    "dupes": "dupes",
    "update": "update",
    "uninstall": "uninstall",
    "log": "log",
}

# Palette roles usable as icon colors.
_ROLES = ("text", "muted", "faint", "accent", "success", "warning", "error",
          "on_accent")

_ICON_SIZE = 18          # logical px shared by buttons and list rows
_RENDER_SIZE = 64        # render large once; QIcon scales smoothly

_cache: dict[tuple[str, str], QIcon] = {}
_dark = True


def set_icon_theme(dark: bool) -> None:
    """Switch the palette the icons are colored with.

    Args:
        dark: True for the dark palette, False for light.
    """
    global _dark
    if _dark != dark:
        _dark = dark
        _cache.clear()


def _role_color(role: str) -> str:
    """Resolve a palette role to a concrete hex color."""
    if role == "on_accent":
        return "#ffffff"  # always readable on the accent background
    from . import theme

    if role == "accent":
        return getattr(theme, "_active_accent", None) or theme.ACCENT_FALLBACK
    pal = theme.palette(_dark)
    return pal.get(role.upper(), pal["TEXT"])


def _render(name: str, color: str) -> QIcon:
    """Render one SVG icon in the given color as a QIcon.

    Args:
        name: Icon name in _ICONS.
        color: Hex color string for the stroke.

    Returns:
        QIcon: The rendered icon.
    """
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'fill="none" stroke="{color}" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f'{_ICONS.get(name, _ICONS["file"])}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pm = QPixmap(_RENDER_SIZE, _RENDER_SIZE)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    icon_obj = QIcon(pm)
    return icon_obj


def icon(name: str, role: str = "text") -> QIcon:
    """The themed icon for `name` colored with the given palette role.

    Args:
        name: Icon name (see _ICONS).
        role: Palette role ("text", "muted", "accent", ...).

    Returns:
        QIcon: A cached, theme-colored icon.
    """
    if role not in _ROLES:
        role = "text"
    key = (name, role)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    built = _render(name, _role_color(role))
    _cache[key] = built
    return built


def nav(name: str) -> QIcon:
    """Sidebar icon: normal state uses TEXT, checked state uses white.

    Args:
        name: Icon name (see NAV_ICONS).

    Returns:
        QIcon: Icon with distinct Normal/Off and Normal/On pixmaps.
    """
    base = icon(name, "text")
    on_key = (name, "__on_white__")
    white = _cache.get(on_key)
    if white is None:
        white = _render(name, "#ffffff")
        _cache[on_key] = white
    combined = QIcon(base.pixmap(_RENDER_SIZE, _RENDER_SIZE))
    combined.addPixmap(white.pixmap(_RENDER_SIZE, _RENDER_SIZE),
                       QIcon.Mode.Normal, QIcon.State.On)
    return combined


def apply(widget, name: str, role: str = "text") -> None:
    """Set a themed icon on a button-like widget at the standard size.

    Args:
        widget: Any widget exposing setIcon/setIconSize (QPushButton...).
        name: Icon name.
        role: Palette role for the color.
    """
    widget.setIcon(icon(name, role))
    widget.setIconSize(icon_size())


def pixmap(name: str, size: int = _ICON_SIZE,
           role: str = "text") -> QPixmap:
    """A crisp pixmap at exactly `size` logical pixels.

    The 64px master render is downscaled and tagged with a 2x
    device-pixel-ratio so labels display it at the requested logical
    size on any DPI setting (fixes oversized, non-rescaling icons).

    Args:
        name: Icon name.
        size: Logical pixel size.
        role: Palette role for the color.

    Returns:
        QPixmap: A size x size (logical) icon pixmap.
    """
    pm = icon(name, role).pixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2.0)
    return pm


def icon_size():
    """The standard logical icon size as a QSize."""
    from PySide6.QtCore import QSize
    return QSize(_ICON_SIZE, _ICON_SIZE)


def _qsize():
    """Deprecated alias kept for internal callers."""
    return icon_size()
