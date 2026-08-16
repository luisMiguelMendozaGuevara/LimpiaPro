"""Fluent style (Windows 11): Mica backdrop, system accent color, fonts
and application icons extracted with GDI+ through ctypes (no external
dependencies)."""

import base64
import ctypes
import os
import platform
import tempfile
import tkinter as _tk
import winreg

import customtkinter as ctk
from ctypes import wintypes

from .uninstall import split_command

FONT_FAMILY = "Segoe UI Variable Text"
FONT_FAMILY_FALLBACK = "Segoe UI"


def _win_version_build():
    """Windows build number (last component of platform.version())."""
    try:
        return int(platform.version().split(".")[-1])
    except Exception:
        return 0


def apply_mica_backdrop(window):
    """Apply the Mica material (translucent, Windows 11 style) to a
    window. Requires Windows 11 22H2+ (build 22621+); a no-op otherwise."""
    try:
        build = _win_version_build()
        if build < 22621:
            return False
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        # DWMWA_SYSTEMBACKDROP_TYPE = 38 ; DWM_SYSTEMBACKDROP_TYPE_MICA = 2
        backdrop = ctypes.c_int(2)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 38, ctypes.byref(backdrop), ctypes.sizeof(backdrop))
        return True
    except Exception:
        return False


def get_system_accent():
    """Read the Windows accent color (DWM) as #RRGGBB. Returns the Fluent
    blue (#0067c0) when it cannot be read."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\DWM") as key:
            val, _ = winreg.QueryValueEx(key, "AccentColor")
        # DWORD stored as 0x00BBGGRR -> convert to #RRGGBB
        r = (val >> 16) & 0xFF
        g = (val >> 8) & 0xFF
        b = val & 0xFF
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#0067c0"


_FONT_CACHE = {}


def fluent_font(size=13, weight="normal"):
    """Segoe UI Variable font with fallback to Segoe UI.

    CTkFont instances are cached by (size, weight): creating them is
    expensive and tkinter also needs the references kept alive."""
    key = (size, weight)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
        _FONT_CACHE[key] = font
    return font


# --------------------------------------------------------------------------
# Application icons (GDI+ via ctypes)
# --------------------------------------------------------------------------

class _GdiplusStartupInput(ctypes.Structure):
    """GDI+ initialization parameters (version 1, default callbacks)."""
    _fields_ = [('GdiplusVersion', ctypes.c_ulong),
                ('DebugEventCallback', ctypes.c_void_p),
                ('SuppressBackgroundThread', ctypes.c_bool),
                ('SuppressExternalCodecs', ctypes.c_bool)]


_PNG_CLSID = (ctypes.c_ubyte * 16)(0x06, 0xF4, 0x7C, 0x55, 0x04, 0x1A, 0xD3, 0x11,
                                   0x9A, 0x73, 0x00, 0x00, 0xF8, 0x1E, 0xF3, 0x2E)


def _extract_exe_from_command(command):
    """Executable path of a startup command (None when unparseable)."""
    argv, _err = split_command(command)
    if argv:
        return argv[0]
    return None


def get_file_icon_png(target, size=16):
    """PNG bytes (`size` x `size`) of a file/folder/shortcut icon, using
    the Windows API (SHGetFileInfo + GDI+). None on failure.

    Pipeline per call: SHGetFileInfoW gives an HICON; GDI+ converts it to
    a bitmap, downscales with HQ bicubic when needed and encodes to PNG
    through a temp file (GDI+ has no in-memory PNG encoder binding here).
    Every handle is released in finally blocks; extraction is meant to be
    called off the UI thread (see IconCache)."""
    try:
        if not target or not os.path.exists(os.path.expandvars(target)):
            return None
        path = os.path.expandvars(target)

        class SHFILEINFO(ctypes.Structure):
            _fields_ = [('hIcon', wintypes.HICON),
                        ('iIcon', ctypes.c_int),
                        ('dwAttributes', ctypes.cDWORD),
                        ('szDisplayName', ctypes.c_wchar * 260),
                        ('szTypeName', ctypes.c_wchar * 80)]

        sfi = SHFILEINFO()
        SHGFI_ICON = 0x100
        SHGFI_LARGEICON = 0x0
        if not ctypes.windll.shell32.SHGetFileInfoW(
                path, 0, ctypes.byref(sfi), ctypes.sizeof(sfi),
                SHGFI_ICON | SHGFI_LARGEICON):
            return None
        hicon = sfi.hIcon
        if not hicon:
            return None
        try:
            gdiplus = ctypes.windll.gdiplus
            token = ctypes.c_ulong(0)
            inp = _GdiplusStartupInput()
            inp.GdiplusVersion = 1
            if gdiplus.GdiplusStartup(ctypes.byref(token), ctypes.byref(inp), None) != 0:
                return None
            try:
                bitmap = ctypes.c_void_p()
                if gdiplus.GdipCreateBitmapFromHICON(hicon, ctypes.byref(bitmap)) != 0:
                    return None
                tmp = os.path.join(tempfile.gettempdir(),
                                   f"lp_icon_{os.getpid()}.png")
                try:
                    # Downscale to `size` x `size` when the icon is larger.
                    w = ctypes.c_uint()
                    gdiplus.GdipGetImageWidth(bitmap, ctypes.byref(w))
                    if w.value > size:
                        PIXEL_32ARGB = 0x0026200A
                        small = ctypes.c_void_p()
                        gdiplus.GdipCreateBitmapFromScan0(size, size, 0, PIXEL_32ARGB,
                                                          None, ctypes.byref(small))
                        graphics = ctypes.c_void_p()
                        gdiplus.GdipGetImageGraphicsContext(small, ctypes.byref(graphics))
                        gdiplus.GdipSetInterpolationMode(graphics, 7)  # HQ Bicubic
                        gdiplus.GdipDrawImageRectI(graphics, bitmap, 0, 0, size, size)
                        gdiplus.GdipSaveImageToFile(small, tmp, ctypes.byref(_PNG_CLSID), None)
                        gdiplus.GdipDisposeImage(graphics)
                        gdiplus.GdipDisposeImage(small)
                    else:
                        gdiplus.GdipSaveImageToFile(bitmap, tmp, ctypes.byref(_PNG_CLSID), None)
                    with open(tmp, "rb") as f:
                        data = f.read()
                    return data
                finally:
                    gdiplus.GdipDisposeImage(bitmap)
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            finally:
                gdiplus.GdiplusShutdown(token)
        finally:
            ctypes.windll.user32.DestroyIcon(hicon)
    except Exception:
        return None


class IconCache:
    """PhotoImage cache keyed by target path (avoids re-extracting icons
    and keeps the references alive -- tkinter garbage-collects images that
    lose their last Python reference).

    PNG bytes are extracted off the UI thread (get_file_icon_png is
    called from workers); PhotoImages are always created on the UI thread
    through _photo."""

    def __init__(self, size=16):
        self.cache = {}
        self.size = size

    def _photo(self, png_bytes):
        """Build a PhotoImage from PNG bytes (base64: what PhotoImage's
        data= parameter expects; raw bytes raise)."""
        try:
            return _tk.PhotoImage(data=base64.b64encode(png_bytes))
        except Exception:
            return None

    def get(self, target):
        """PhotoImage for a startup command's executable (None when the
        command has no resolvable executable or extraction fails)."""
        if not target:
            return None
        path = os.path.expandvars(_extract_exe_from_command(target) or "")
        if not path or not os.path.exists(path):
            return None
        if path in self.cache:
            return self.cache[path]
        data = get_file_icon_png(path)
        if not data:
            return None
        img = self._photo(data)
        if img is None:
            return None
        self.cache[path] = img
        return img
