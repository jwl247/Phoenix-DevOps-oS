# -*- mode: python ; coding: utf-8 -*-
# Build: pyinstaller tools/phoenix-tray.spec (from anywhere) — the script path
# is resolved next to this spec via PyInstaller's SPECPATH (S34OPS-F25; it used
# to assume a build from the repo's parent directory).
import os


a = Analysis(
    [os.path.join(SPECPATH, 'phoenix-tray.py')],
    pathex=[],
    binaries=[],
    datas=[],
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
    name='phoenix-tray',
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
)
