# -*- mode: python ; coding: utf-8 -*-
# LimpiaPro data files: the PySide6 stylesheet (theme.py reads it next to
# the compiled module), the community rules and the app icon (both are
# located via app_dir() = the folder holding the exe when frozen).
import os
import sys

sys.path.insert(0, SPECPATH)
sys.path.insert(0, os.path.join(SPECPATH, "installer"))

from limpiapro import APP_NAME, APP_VERSION  # noqa: E402
from pyinstaller_common import trim_unused_qt, write_version_file  # noqa: E402

datas = []
datas += [
    ('limpiapro/ui/resources/style.qss', 'limpiapro/ui/resources'),
    ('winapp2.ini', '.'),
    ('assets/limpiadora.ico', 'assets'),
]


a = Analysis(
    ['limpiador.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Drop the Qt components a widget-only app never loads (~40 MB less).
for _name in trim_unused_qt(a):
    print(f"trimmed unused Qt component: {_name}")
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LimpiaPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX OFF: compressed exes are a well-known antivirus false-positive
    # trigger (unsigned app + UPX = heuristic quarantine). The size win
    # does not pay for the AV friction; checksums cover integrity.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/limpiadora.ico'],
    # Author/product metadata (CompanyName, FileVersion...): a frozen exe
    # with an empty version resource looks anonymous to Windows and AV.
    version=write_version_file(os.path.join(WORKPATH, "version_info"),
                               APP_NAME, APP_VERSION, "LimpiaPro.exe"),
)



