from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
from pathlib import Path

import pytest

from app.version import get_version

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def release():
    return runpy.run_path(str(ROOT / "build" / "release.py"))


def mock_git(monkeypatch, *, commit="abc123", tagged="abc123", status="", files="", lfs=""):
    def check_output(command, **kwargs):
        if command[1:] == ["rev-parse", "HEAD"]:
            return commit
        if command[1] == "rev-parse":
            return tagged
        if command[1] == "status":
            return status
        if command[1:3] == ["ls-files", "--stage"]:
            return lfs if "--" in command else files
        raise AssertionError(command)

    monkeypatch.setattr(subprocess, "check_output", check_output)


def test_release_source_must_match_clean_tag(release, monkeypatch):
    tag = f"v{get_version()}"
    mock_git(monkeypatch)
    assert release["validate_source_tag"](tag) == "abc123"
    mock_git(monkeypatch, tagged="other-commit")
    with pytest.raises(ValueError, match="checked-out commit"):
        release["validate_source_tag"](tag)
    for status in (" M app/main.py", "?? new_source.py"):
        mock_git(monkeypatch, status=status)
        with pytest.raises(ValueError, match="clean worktree"):
            release["validate_source_tag"](tag)
    mock_git(monkeypatch, files="160000 deadbeef 0\tvendor/submodule")
    with pytest.raises(ValueError, match="submodules"):
        release["validate_source_tag"](tag)
    mock_git(monkeypatch, lfs="100644 deadbeef 0\tlarge-resource.bin")
    with pytest.raises(ValueError, match="Git LFS"):
        release["validate_source_tag"](tag)


def test_release_assets_hash_final_installer_and_all_downloads(release, workdir, monkeypatch):
    mock_git(monkeypatch)
    version = get_version()
    tag = f"v{version}"
    asset = workdir / f"Playgrounds-{version}-x64.msi"
    asset.write_bytes(b"final signed MSI bytes")
    output = workdir / "release"

    def archive(command, **kwargs):
        assert command[-1] == f"refs/tags/{tag}"
        assert "--format=zip" in command
        assert f"--prefix=Playgrounds-{version}/" in command
        assert kwargs["check"] is True
        archive_path = next(item.removeprefix("--output=") for item in command if item.startswith("--output="))
        Path(archive_path).write_bytes(b"source at exact tag")

    monkeypatch.setattr(subprocess, "run", archive)
    release["write_release_assets"](asset, output, tag=tag, notes="Changes")
    assert (output / asset.name).read_bytes() == asset.read_bytes()
    manifest = json.loads((output / "update.json").read_text(encoding="utf-8"))
    assert manifest["sha256"] == hashlib.sha256(asset.read_bytes()).hexdigest()
    assert manifest["notes"] == "Changes"
    environment = json.loads((output / "build-environment.json").read_text(encoding="utf-8"))
    assert environment["commit"] == "abc123"
    assert environment["tag"] == tag
    assert "PyQt6" in environment["packages"]
    checksums = (output / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    assert len(checksums) == 4
    for line in checksums:
        digest, name = line.split("  ")
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == digest
    with pytest.raises(ValueError, match="must be empty"):
        release["write_release_assets"](asset, output, tag=tag)


def test_release_packaging_rejects_wrong_asset(release, workdir, monkeypatch):
    mock_git(monkeypatch)
    with pytest.raises(ValueError, match="built MSI"):
        release["write_release_assets"](
            workdir / "wrong.msi", workdir / "release", tag=f"v{get_version()}",
        )
    assert not (workdir / "release").exists()


@pytest.mark.parametrize(
    "arguments",
    [["--check-source"], ["--package-release"], ["--package-release", "--release-tag", f"v{get_version()}"]],
)
def test_cli_requires_release_inputs(release, monkeypatch, arguments):
    monkeypatch.setattr("sys.argv", ["release.py", *arguments])
    with pytest.raises(SystemExit) as error:
        release["main"]()
    assert error.value.code == 2
