"""Collect installed runtime license texts for the frozen Windows application."""

from __future__ import annotations

import importlib.metadata
import sys
from pathlib import Path, PurePosixPath


def distribution_licenses(name: str) -> list[tuple[str, str]]:
    distribution = importlib.metadata.distribution(name)
    files = []
    for entry in distribution.files or ():
        parts = PurePosixPath(str(entry).replace("\\", "/")).parts
        if not any(part.endswith(".dist-info") for part in parts):
            continue
        index = next(index for index, part in enumerate(parts) if part.endswith(".dist-info"))
        relative = PurePosixPath(*parts[index + 1:])
        if ".." in relative.parts:
            raise ValueError(f"Unsafe license path in {name}: {entry}")
        if not (relative.name.lower().startswith(("license", "copying", "notice", "authors"))
                or "licenses" in relative.parts):
            continue
        source = Path(distribution.locate_file(entry))
        if not source.is_file():
            raise FileNotFoundError(f"Missing {name} license: {source}")
        files.append((str(source), str(PurePosixPath("licenses", name, relative.parent))))
    if not files:
        raise FileNotFoundError(f"No license texts found in installed {name} distribution")
    return files


def collect_license_datas(output: Path) -> list[tuple[str, str]]:
    names = ["PyQt6", "PyQt6-Qt6", "PyQt6-sip", "PyInstaller"]
    if sys.version_info < (3, 11):
        names.append("tomli")
    files = []
    notices = [
        "Playgrounds third-party notices",
        "",
        "These are license texts from the exact installed build dependencies.",
        "PyInstaller is included for its embedded bootloader and license exception.",
        "Project license: see ../LICENSE. Asset licenses: see ../app/resources/.",
        "Corresponding source and third-party components must be reviewed before release.",
        "",
    ]
    for name in names:
        files.extend(distribution_licenses(name))
        notices.append(f"{name} {importlib.metadata.version(name)}: {name}/")
    python_license = next((
        path for path in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE")
        if path.is_file()
    ), None)
    if python_license is None:
        raise FileNotFoundError(f"Python license not found under {sys.base_prefix}")
    files.append((str(python_license), "licenses/Python"))
    notices.append(f"Python {sys.version.split()[0]}: Python/{python_license.name}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(notices) + "\n", encoding="utf-8")
    files.append((str(output), "licenses"))
    return files
