"""Lightweight internationalization (Spanish / English).

The UI language is chosen once at import time from the Windows display
language (GetUserDefaultUILanguage). Spanish Windows gets Spanish, anything
else gets English. The LIMPIAPRO_LANG environment variable overrides the
detection, which is handy for development and tests.

Design rules:
  - Every user-facing string lives here as a key; UI code calls t(key).
  - Values are plain ASCII (no accents), following the project convention.
  - Placeholders use str.format syntax: t("log.winapp_loaded", n=3, path=p).
  - Backend modules return stable English/ASCII status strings; the UI
    layer translates them for display (architecture rule).
"""

import ctypes
import locale as _locale
import os

from ..utils import _errlog
from .en import STRINGS as _EN
from .es import STRINGS as _ES

# Internal fallback chain when a key is missing from the active language
# table: current language -> Spanish (the project's original language).
_STRINGS = {"es": _ES, "en": _EN}


def detect_language():
    """Return the UI language code: "es" (Spanish Windows) or "en" (anything
    else, English being the fallback lingua franca).

    Resolution order:
      1. LIMPIAPRO_LANG environment variable (development/testing override).
      2. GetUserDefaultUILanguage(): primary language id 10 == Spanish.
      3. locale.getdefaultlocale() as a last resort if the Win32 call fails.
    """
    override = (os.environ.get("LIMPIAPRO_LANG") or "").strip().lower()
    if override[:2] in _STRINGS:
        return override[:2]
    try:
        # Primary language id: the low 10 bits of the LANGID.
        if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 10:
            return "es"
        return "en"
    except Exception:
        try:
            loc = (_locale.getdefaultlocale()[0] or "").lower()
        except Exception:
            loc = ""
        return "es" if loc.startswith("es") else "en"


LANG = detect_language()


def set_language(code: str) -> None:
    """Switch the UI language at runtime (settings page).

    New t() calls use the new language; already-built widgets keep their
    text until the window is rebuilt/restarted."""
    global LANG
    code = (code or "").strip().lower()[:2]
    LANG = code if code in _STRINGS else detect_language()


def t(key, **fmt):
    """Translate `key` into the active language, formatting placeholders.

    Missing keys fall back to Spanish, then to the key itself (and leave a
    trace in the error log so gaps are easy to spot). With no `fmt` the
    string is returned as-is, avoiding format errors on literal braces.
    """
    text = _STRINGS.get(LANG, {}).get(key)
    if text is None:
        text = _STRINGS["es"].get(key)
    if text is None:
        _errlog(f"i18n: missing translation key '{key}'")
        return key
    return text.format(**fmt) if fmt else text
