# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# pywebview 관련 숨겨진 import 수집
hidden = collect_submodules('webview')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('ui', 'ui'),          # HTML/CSS 파일 포함
        ('api', 'api'),        # api 패키지 포함
    ],
    hiddenimports=hidden + [
        'webview.platforms.winforms',  # Windows
        'clr',                         # pythonnet (Windows pywebview 의존성)
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RVMParser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # 콘솔 창 숨김 (GUI 앱)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='ui/icon.ico',   # 아이콘 파일이 있으면 주석 해제
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RVMParser',
)
