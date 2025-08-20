# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
<<<<<<< HEAD
    datas=[('templates', 'templates'), ('instance/instance_data.db', '.')],
=======
    datas=[],
>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb
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
    name='app',
    debug=False,
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
<<<<<<< HEAD
    icon=['gbt.png'],
=======
>>>>>>> 9823f2e49f8fad873f50c5a3321e708833d8c6cb
)
