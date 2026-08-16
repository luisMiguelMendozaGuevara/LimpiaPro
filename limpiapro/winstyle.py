"""Estilo Fluent (Windows 11): fondo Mica, color de acento, fuentes e
iconos de aplicaciones extraidos con GDI+ via ctypes (sin dependencias
externas)."""

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
    try:
        return int(platform.version().split(".")[-1])
    except Exception:
        return 0


def apply_mica_backdrop(window):
    """Aplica el material Mica (translucido, estilo Windows 11) a la ventana.
    Requiere Windows 11 22H2+ (build 22621+). Si no hay soporte, no hace nada."""
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
    """Lee el color de acento de Windows (DWM) como hex #RRGGBB.
    Devuelve un azul Fluent (#0067c0) si no se puede leer."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\DWM") as key:
            val, _ = winreg.QueryValueEx(key, "AccentColor")
        # DWORD en formato 0x00BBGGRR -> convertir a #RRGGBB
        r = (val >> 16) & 0xFF
        g = (val >> 8) & 0xFF
        b = val & 0xFF
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#0067c0"


_FONT_CACHE = {}


def fluent_font(size=13, weight="normal"):
    """Fuente Segoe UI Variable con fallback a Segoe UI.

    La instancia CTkFont se cachea por (size, weight): crearla es costoso
    y ademas mantiene referencias vivas que tkinter necesita."""
    key = (size, weight)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)
        _FONT_CACHE[key] = font
    return font


# --------------------------------------------------------------------------
# Iconos de aplicaciones (GDI+ via ctypes)
# --------------------------------------------------------------------------

class _GdiplusStartupInput(ctypes.Structure):
    _fields_ = [('GdiplusVersion', ctypes.c_ulong),
                ('DebugEventCallback', ctypes.c_void_p),
                ('SuppressBackgroundThread', ctypes.c_bool),
                ('SuppressExternalCodecs', ctypes.c_bool)]


_PNG_CLSID = (ctypes.c_ubyte * 16)(0x06, 0xF4, 0x7C, 0x55, 0x04, 0x1A, 0xD3, 0x11,
                                   0x9A, 0x73, 0x00, 0x00, 0xF8, 0x1E, 0xF3, 0x2E)


def _extract_exe_from_command(command):
    """Extrae la ruta del ejecutable de un comando de inicio."""
    argv, _err = split_command(command)
    if argv:
        return argv[0]
    return None


def get_file_icon_png(target, size=16):
    """Devuelve bytes PNG (tamano `size`) del icono de un archivo/carpeta/acceso
    directo. Usa la API de Windows (SHGetFileInfo + GDI+). None si falla."""
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
                    # Redimensionar a `size` x `size` si el icono es mayor
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
    """Cache de PhotoImage de iconos por ruta (evita re-extraer y mantiene
    referencias vivas, necesario para que tkinter no las recoja).

    La extraccion de bytes PNG se hace fuera del hilo de UI
    (get_file_icon_png); los PhotoImage se crean siempre desde el hilo UI
    via _photo."""

    def __init__(self, size=16):
        self.cache = {}
        self.size = size

    def _photo(self, png_bytes):
        try:
            # PhotoImage(data=...) espera base64, no bytes crudos.
            return _tk.PhotoImage(data=base64.b64encode(png_bytes))
        except Exception:
            return None

    def get(self, target):
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
