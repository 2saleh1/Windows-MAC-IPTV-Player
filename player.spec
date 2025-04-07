# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['player.py'],
    pathex=[],
    binaries=[
        ('C:/ffmpeg/ffplay.exe', '.'),
        ('C:/ffmpeg/ffmpeg.exe', '.'),
    ],
    datas=[('credentials', 'credentials')],
    hiddenimports=['sys'],  # Explicitly include sys module
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='IPTV_Player',
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
    icon='assets/IPTV_PLAYER.ico'
)