# -*- mode: python ; coding: utf-8 -*-

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(SPECPATH, "app.ico")
VERSION = os.path.join(SPECPATH, "version_info.txt")

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "pytest",
        "ruff",
        "setuptools",
        "pip",
        "PySide6",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

_TRIM_BINARIES = (
    "opengl32sw.dll",
    "libcrypto-3.dll",
    "libssl-3.dll",
    "qopensslbackend.dll",
)


def _normalize(name: str) -> str:
    return name.replace("\\", "/").lower()


a.binaries = [
    entry for entry in a.binaries
    if not any(_normalize(entry[0]).endswith(name) for name in _TRIM_BINARIES)
]
a.datas = [
    entry for entry in a.datas
    if "/translations/" not in _normalize(entry[0])
]

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Playgrounds",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=ICON if os.path.exists(ICON) else None,
    version=VERSION if os.path.exists(VERSION) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Playgrounds",
)
