# -*- mode: python ; coding: utf-8 -*-
# LimpiaPro portable (OneDir): starts instantly because Windows loads the
# binaries straight from disk instead of unpacking a 60 MB one-file archive
# to %TEMP% on every launch. Distributed as a zip asset in the release.
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('customtkinter')
# LimpiaPro data files: the PySide6 stylesheet (theme.py reads it next to
# the compiled module), the community rules and the app icon (both are
# located via app_dir() = the folder holding the exe when frozen).
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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LimpiaPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/limpiadora.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='LimpiaProPortable',
)

