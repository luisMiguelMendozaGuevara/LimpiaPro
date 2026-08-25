# -*- mode: python ; coding: utf-8 -*-
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
    a.binaries,
    a.datas,
    [],
    name='LimpiaPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/limpiadora.ico'],
)

