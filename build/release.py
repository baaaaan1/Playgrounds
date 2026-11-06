"""Generate Windows version resources and verified GitHub release assets."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.version import get_version, validate_msi_version  # noqa: E402


def validate_release_tag(version: str, tag: str | None = None) -> str:
    """Return a matching tag; default to vVERSION, allow VERSION or vVERSION."""
    validate_msi_version(version)
    if tag is None:
        return f"v{version}"
    if tag not in (version, f"v{version}"):
        raise ValueError(f"Release tag {tag!r} does not match version {version}")
    return tag


def generate_version_info(output: Path) -> str:
    version = get_version()
    parts = validate_msi_version(version)
    template = (ROOT / "build" / "version_info.txt").read_text(encoding="utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        template.format(version=version, version_tuple=(*parts, 0)), encoding="utf-8"
    )
    return version


def write_update_manifest(
    asset: Path, output: Path, *, tag: str | None = None, notes: str = ""
) -> dict[str, str]:
    version = get_version()
    tag = validate_release_tag(version, tag)
    expected_name = f"Playgrounds-{version}-x64.msi"
    if asset.name != expected_name:
        raise ValueError(f"Expected release asset {expected_name}, got {asset.name}")
    manifest = {
        "version": version,
        "url": f"https://github.com/baaaaan1/Playgrounds/releases/download/{tag}/{asset.name}",
        "sha256": sha256_file(asset),
        "notes": notes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source_tag(tag: str) -> str:
    """Only release committed, clean sources at the version's exact tag."""
    validate_release_tag(get_version(), tag)

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8",
        ).strip()

    commit = git("rev-parse", "HEAD")
    if git("rev-parse", f"refs/tags/{tag}^{{commit}}") != commit:
        raise ValueError("Release tag must point to the checked-out commit")
    if git("status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("Release requires a clean worktree, including untracked source files")
    if git("ls-files", "--stage", "--", ":(attr:filter=lfs)") or "160000 " in git("ls-files", "--stage"):
        raise ValueError("Source archive does not support Git LFS or submodules")
    return commit


def write_release_assets(asset: Path, output: Path, *, tag: str, notes: str = "") -> None:
    """Package the final (optionally signed) MSI; never sign after this step."""
    commit = validate_source_tag(tag)
    version = get_version()
    if asset.name != f"Playgrounds-{version}-x64.msi" or not asset.is_file():
        raise ValueError("A built MSI matching the project version is required")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Release output directory must be empty to prevent stale assets")
    output.mkdir(parents=True, exist_ok=True)
    installer = output / asset.name
    shutil.copy2(asset, installer)
    write_update_manifest(installer, output / "update.json", tag=tag, notes=notes)
    source = output / f"Playgrounds-{version}-source.zip"
    subprocess.run(
        ["git", "-c", "core.autocrlf=false", "archive", "--format=zip",
         f"--prefix=Playgrounds-{version}/", f"--output={source.resolve()}", f"refs/tags/{tag}"],
        cwd=ROOT, check=True,
    )
    environment = {
        "version": version, "tag": tag, "commit": commit,
        "python": sys.version, "platform": platform.platform(),
        "packages": dict(sorted(
            (dist.metadata["Name"], dist.version)
            for dist in importlib.metadata.distributions() if dist.metadata["Name"]
        )),
    }
    (output / "build-environment.json").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8",
    )
    assets = sorted(path for path in output.iterdir() if path.is_file())
    (output / "SHA256SUMS.txt").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in assets), encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-tag")
    parser.add_argument("--asset", type=Path)
    parser.add_argument("--notes", default="")
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / "update.json")
    parser.add_argument("--check-source", action="store_true")
    parser.add_argument("--package-release", action="store_true")
    parser.add_argument("--release-dir", type=Path, default=ROOT / "dist" / "release")
    args = parser.parse_args()
    version = get_version()
    validate_release_tag(version, args.release_tag)
    if (args.check_source or args.package_release) and not args.release_tag:
        parser.error("--release-tag is required for release source verification")
    if args.check_source:
        validate_source_tag(args.release_tag)
    if args.package_release:
        if not args.asset:
            parser.error("--asset is required for --package-release")
        write_release_assets(args.asset, args.release_dir, tag=args.release_tag, notes=args.notes)
    elif args.asset:
        write_update_manifest(args.asset, args.output, tag=args.release_tag, notes=args.notes)
    print(version)


if __name__ == "__main__":
    main()
