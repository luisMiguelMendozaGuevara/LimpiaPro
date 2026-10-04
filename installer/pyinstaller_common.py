"""Shared PyInstaller helpers for the LimpiaPro specs.

Two build-time concerns that belong in one place:

1. VERSION RESOURCE: a frozen exe with no CompanyName/FileVersion looks
   anonymous to Windows, Explorer and antivirus heuristics. write_version_
   file() produces the VSVersionInfo that every spec passes to EXE(), so the
   metadata always matches limpiapro.APP_VERSION.

2. SIZE TRIM: PySide6 ships the whole Qt stack; a widget-only app never
   loads QML/Quick/PDF/Network/VirtualKeyboard nor the 20 MB software
   OpenGL fallback. Dropping them shrinks the download ~40%, speeds up the
   install and gives antivirus less to scan.
"""

from __future__ import annotations

import os
import re

# Bundled Qt pieces the UI never uses (lower-case substring match on the
# destination path). Keep this list conservative: only components that a
# pure QtWidgets application cannot load.
UNUSED_QT_MARKERS = (
    "opengl32sw",                 # 20 MB software OpenGL fallback
    "qt6quick",                   # QML Quick runtime
    "qt6qml",                     # QML engine
    "qt6pdf",                     # Qt PDF
    "qt6network",                 # no networking in the app
    "qt6virtualkeyboard",         # on-screen keyboard
    "plugins/tls",                # TLS backend (needs QtNetwork)
    "plugins/networkinformation",  # network info (needs QtNetwork)
    "plugins/platforminputcontexts",  # virtual keyboard integration
    "qml",                        # QML import tree
    "qtquick",
)

COMPANY_NAME = "Luis Miguel Mendoza Guevara"
PRODUCT_NAME = "LimpiaPro"
COPYRIGHT = "Copyright (c) 2026 Luis Miguel Mendoza Guevara. MIT License."


def parse_version(version: str) -> tuple[int, int, int, int]:
    """'2.11.3' -> (2, 11, 3, 0): the four ints the version resource needs."""
    parts = [int(p) for p in re.findall(r"\d+", version)[:4]]
    return tuple([*parts, 0, 0, 0, 0][:4])  # type: ignore[return-value]


def version_file_text(app_name: str, version: str, exe_name: str) -> str:
    """The VSVersionInfo content for a frozen executable."""
    numbers = parse_version(version)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{COMPANY_NAME}'),
        StringStruct('FileDescription', '{PRODUCT_NAME} - {app_name}'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', '{PRODUCT_NAME}'),
        StringStruct('LegalCopyright', '{COPYRIGHT}'),
        StringStruct('OriginalFilename', '{exe_name}'),
        StringStruct('ProductName', '{PRODUCT_NAME}'),
        StringStruct('ProductVersion', '{version}')])
      ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def write_version_file(directory: str, app_name: str, version: str,
                       exe_name: str) -> str:
    """Write the version resource next to the build and return its path."""
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"version_info_{app_name}.txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(version_file_text(app_name, version, exe_name))
    return path


def trim_unused_qt(analysis) -> list[str]:
    """Drop the unused Qt components from an Analysis (binaries + datas).

    Args:
        analysis: The PyInstaller Analysis object (mutated in place).

    Returns:
        list[str]: The names that were removed (for the build log).
    """
    removed: list[str] = []

    def _keep(entry) -> bool:
        name = str(entry[0]).replace("\\", "/").lower()
        if any(marker in name for marker in UNUSED_QT_MARKERS):
            removed.append(entry[0])
            return False
        return True

    analysis.binaries = [b for b in analysis.binaries if _keep(b)]
    analysis.datas = [d for d in analysis.datas if _keep(d)]
    return removed
