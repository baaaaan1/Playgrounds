# -*- mode: python ; coding: utf-8 -*-

import os
import runpy
from pathlib import Path

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
ICON = os.path.join(SPECPATH, "app.ico")
VERSION = os.path.join(SPECPATH, "generated", "version_info.txt")
release = runpy.run_path(os.path.join(SPECPATH, "release.py"))
release["generate_version_info"](release["Path"](VERSION))
licenses = runpy.run_path(os.path.join(SPECPATH, "licenses.py"))
LICENSES = licenses["collect_license_datas"](
    Path(SPECPATH) / "generated" / "THIRD_PARTY_NOTICES.txt"
)
CATALOGS = [
    (str(path), "app/resources/i18n")
    for path in sorted((Path(ROOT) / "app/resources/i18n").glob("playgrounds_*.qm"))
]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(SPECPATH, "icon.svg"), "build"),
        (os.path.join(SPECPATH, "qr-code.svg"), "build"),
        (os.path.join(ROOT, "app", "resources", "line-md"), "app/resources/line-md"),
        (os.path.join(ROOT, "app", "resources", "material-symbols"), "app/resources/material-symbols"),
        (os.path.join(ROOT, "pyproject.toml"), "app"),
        (os.path.join(ROOT, "LICENSE"), "."),
    ] + CATALOGS + LICENSES,
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
    version=VERSION,
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
