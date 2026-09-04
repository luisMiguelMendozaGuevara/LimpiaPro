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
import os
import sys

from ..utils import _errlog
from .en import STRINGS as _EN
from .es import STRINGS as _ES

# Internal fallback chain when a key is missing from the active language
# table: current language -> Spanish (the project's original language).
_STRINGS = {"es": _ES, "en": _EN}

_WIN = sys.platform == "win32"

# LOCALE_NAME_MAX_LENGTH from the Win32 API (limits GetUserDefaultLocaleName
# buffers).
_LOCALE_NAME_MAX = 85


def _system_locale_name() -> str:
    """Best-effort BCP-47 locale name without deprecated APIs.

    Windows: GetUserDefaultLocaleName (Vista+, the modern replacement for
    locale.getdefaultlocale(), which is deprecated and slated for removal).
    Elsewhere: the standard locale environment variables, in gettext's
    precedence order. Empty string when nothing can be determined.
    """
    if _WIN:
        name = ""
        try:
            buf = ctypes.create_unicode_buffer(_LOCALE_NAME_MAX)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(
                    buf, _LOCALE_NAME_MAX):
                name = buf.value
        except Exception:
            name = ""  # best-effort: the env-var lookup below still runs
        if name:
            return name
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var)
        # "C"/"POSIX" mean "neutral locale": the deprecated
        # locale.getdefaultlocale() mapped them to (None, None), so they
        # must fall through to the next variable, not match "es"/"en".
        if val and val not in ("C", "POSIX"):
            return val
    return ""


def detect_language():
    """Return the UI language code: "es" (Spanish Windows) or "en" (anything
    else, English being the fallback lingua franca).

    Resolution order:
      1. LIMPIAPRO_LANG environment variable (development/testing override).
      2. GetUserDefaultUILanguage(): primary language id 10 == Spanish.
      3. _system_locale_name() (GetUserDefaultLocaleName / env vars) as a
         last resort if the Win32 UI-language call fails.
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
            loc = _system_locale_name()
        except Exception:
            loc = ""
        return "es" if loc.lower().startswith("es") else "en"


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
