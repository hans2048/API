# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hidden = collect_submodules('webview')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('ui', 'ui'),   # HTML 파일 포함
        ('api', 'api'), # api 패키지 포함
    ],
    hiddenimports=hidden + [
        'webview.platforms.winforms',
        'clr',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# ── 단일 exe (onefile) ──────────────────────────────────────────
# 실행 시 임시 폴더에 압축 해제 → 첫 실행이 수 초 느릴 수 있음
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,   # onefile: binaries를 EXE에 포함
    a.zipfiles,
    a.datas,
    name='RVMParser',
    debug=False,
    strip=False,
    upx=True,
    console=False,        # 콘솔 창 숨김
    # icon='ui/icon.ico', # 아이콘 파일이 있으면 주석 해제
)
