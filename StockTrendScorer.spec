# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['gui_app.py'],
    pathex=[],
    binaries=[('.venv/Library/bin/ffi.dll', '.'), ('.venv/Library/bin/liblzma.dll', '.'), ('.venv/Library/bin/libbz2.dll', '.'), ('.venv/Library/bin/sqlite3.dll', '.'), ('.venv/Library/bin/libexpat.dll', '.'), ('.venv/Library/bin/libssl-3-x64.dll', '.'), ('.venv/Library/bin/libcrypto-3-x64.dll', '.')],
    datas=[('stock_trend_scorer/data/universe', 'stock_trend_scorer/data/universe')],
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
    name='StockTrendScorer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='StockTrendScorer',
)
