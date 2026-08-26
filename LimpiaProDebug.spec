# -*- mode: python ; coding: utf-8 -*-
# LimpiaPro data files: the PySide6 stylesheet (theme.py reads it next to
# the compiled module), the community rules and the app icon (both are
# located via app_dir() = the folder holding the exe when frozen).
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
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='LimpiaProDebug',
    debug=True,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/limpiadora.ico'],
)



