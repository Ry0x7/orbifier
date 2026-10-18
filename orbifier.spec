# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for orbifier.exe
# Build with:  pyinstaller --noconfirm orbifier.spec   (or run build.bat)
#
# Must stay --onefile and self-contained: in frozen mode faker.py copies
# sys.executable itself to create the fake game exes, which re-launch it
# with --timer-mode.

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [('settings.py', '.'), ('docs/orbifier.ico', 'docs')]
binaries = []
hiddenimports = collect_submodules('orbifier') + [
    'settings',
    'tkinter',
    'tkinter.ttk',
    'tkinter.messagebox',
    'tkinter.font',
]

pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all('orbifier')
datas += pkg_datas
binaries += pkg_binaries
hiddenimports += pkg_hiddenimports

a = Analysis(
    ['orbifier.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='orbifier',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon='docs/orbifier.ico',
)
