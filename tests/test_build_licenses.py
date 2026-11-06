from __future__ import annotations

import importlib.metadata
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def licenses():
    return runpy.run_path(str(ROOT / "build" / "licenses.py"))


def fake_distribution(root, files):
    return SimpleNamespace(
        files=[importlib.metadata.PackagePath(path) for path in files],
        locate_file=lambda entry: root / entry,
        version="1.2.3",
    )


def test_license_collection_preserves_nested_license_texts(licenses, workdir, monkeypatch):
    paths = [
        "dependency-1.2.3.dist-info/licenses/LICENSE",
        "dependency-1.2.3.dist-info/licenses/third-party/component.txt",
        "dependency-1.2.3.dist-info/NOTICE.txt",
        "dependency-1.2.3.dist-info/METADATA",
        "dependency/code.py",
    ]
    for path in paths:
        target = workdir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("license text", encoding="utf-8")
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: fake_distribution(workdir, paths))
    collected = licenses["distribution_licenses"]("dependency")
    assert collected == [
        (str(workdir / paths[0]), "licenses/dependency/licenses"),
        (str(workdir / paths[1]), "licenses/dependency/licenses/third-party"),
        (str(workdir / paths[2]), "licenses/dependency"),
    ]


@pytest.mark.parametrize("files", [[], ["dependency-1.0.dist-info/METADATA"]])
def test_missing_license_fails_build(licenses, workdir, monkeypatch, files):
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: fake_distribution(workdir, files))
    with pytest.raises(FileNotFoundError, match="No license texts"):
        licenses["distribution_licenses"]("dependency")


def test_recorded_license_must_exist(licenses, workdir, monkeypatch):
    distribution = fake_distribution(workdir, ["dependency-1.0.dist-info/licenses/LICENSE"])
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: distribution)
    with pytest.raises(FileNotFoundError, match="Missing dependency license"):
        licenses["distribution_licenses"]("dependency")


def test_license_paths_cannot_escape_destination(licenses, workdir, monkeypatch):
    distribution = fake_distribution(workdir, ["dependency-1.0.dist-info/../../LICENSE"])
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: distribution)
    with pytest.raises(ValueError, match="Unsafe license path"):
        licenses["distribution_licenses"]("dependency")


def test_generated_notices_include_runtime_versions_and_python(licenses, workdir, monkeypatch):
    path = "dependency-1.0.dist-info/LICENSE"
    target = workdir / path
    target.parent.mkdir()
    target.write_text("test license", encoding="utf-8")
    (workdir / "LICENSE.txt").write_text("Python license", encoding="utf-8")
    monkeypatch.setattr(importlib.metadata, "distribution", lambda name: fake_distribution(workdir, [path]))
    monkeypatch.setattr(sys, "base_prefix", str(workdir))
    output = workdir / "generated" / "THIRD_PARTY_NOTICES.txt"
    datas = licenses["collect_license_datas"](output)
    text = output.read_text(encoding="utf-8")
    for name in ("PyQt6", "PyQt6-Qt6", "PyQt6-sip", "PyInstaller"):
        assert f"{name} 1.2.3" in text
    assert (str(workdir / "LICENSE.txt"), "licenses/Python") in datas
    assert datas[-1] == (str(output), "licenses")
    (workdir / "LICENSE.txt").unlink()
    with pytest.raises(FileNotFoundError, match="Python license not found"):
        licenses["collect_license_datas"](output)
